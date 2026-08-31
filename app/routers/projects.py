"""项目管理路由"""
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.cache import get as cache_get, set as cache_set, invalidate, invalidate_prefix
from ..core.utils import (
    serialize, serialize_many, get_or_404, schema_data,
    normalize_project_payload, ensure_project_exists,
    account_profile_summary,
)
from ..database import get_db
from ..models import (
    Project, Env, ApiCase, UiCase, UiCaseRevision, UiLocatorMemory, UiRecordPreflight, UiRecordProjectConfig,
    TestRecord, TestAccountBinding, TestAccountProfile, User,
    FunctionalTask, FunctionalCase, FunctionalRun, FunctionalScreenshot,
    FunctionalRequirementNote, FunctionalImpactItem, FunctionalDataCheckResult,
    FunctionalDataCheckRule, PageSnapshot, LocatorHealLog, ActionTemplate,
    CaseGenerationCase, CaseGenerationScreenshot, CaseGenerationRequirementNote, CaseGenerationTask,
    RequirementVerification, VerificationClarification, VerificationDataSource,
    VerificationFormula, VerificationItem, VerificationMaterial, VerificationMemory,
    VerificationRun, VerificationRunDataset, VerificationRunItem,
    VerificationLearningEvent, VerificationLearningSession,
)
from ..schemas import ProjectCreate, ProjectUpdate
from ..security import get_current_user, require_admin

router = APIRouter(tags=["projects"])


@router.get("/api/projects")
def list_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[Dict[str, Any]]:  # type: ignore[name-defined]
    cached = cache_get("projects")
    if cached is not None:
        return cached
    projects = db.query(Project).order_by(Project.id.desc()).all()
    if not projects:
        return []

    project_ids = [p.id for p in projects]

    # 批量加载账号绑定关系（代替逐行查询的 N+1 模式）
    bindings: dict[int, int | None] = {}
    for row in (
        db.query(TestAccountBinding.target_id, TestAccountBinding.account_profile_id)
        .filter(
            TestAccountBinding.target_type == "project",
            TestAccountBinding.target_id.in_(project_ids),
        )
        .all()
    ):
        bindings[row[0]] = row[1]

    # 批量加载所有关联的账号配置
    bound_profile_ids = [pid for pid in bindings.values() if pid is not None]
    profiles_map: dict[int, TestAccountProfile] = {}
    if bound_profile_ids:
        for p in db.query(TestAccountProfile).filter(TestAccountProfile.id.in_(bound_profile_ids)).all():
            profiles_map[p.id] = p

    # 批量获取各项目下的「恰好一条有效账号」作为兜底
    fallback_profile: dict[int, TestAccountProfile] = {}
    for project_id in project_ids:
        projs = (
            db.query(TestAccountProfile)
            .filter(TestAccountProfile.project_id == project_id, TestAccountProfile.status == "active")
            .order_by(TestAccountProfile.id.asc())
            .all()
        )
        if len(projs) == 1:
            fallback_profile[project_id] = projs[0]

    result = []
    for project in projects:
        item = serialize(project)
        profile: TestAccountProfile | None = None
        pid = bindings.get(project.id)
        if pid and pid in profiles_map:
            profile = profiles_map[pid]
        if not profile and project.id in fallback_profile:
            profile = fallback_profile[project.id]
        item.update(account_profile_summary(profile))
        result.append(item)

    cache_set("projects", result, ttl=60)
    return result


@router.post("/api/projects")
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = normalize_project_payload(schema_data(payload), require_name=True)
    project = Project(name=data["name"], desc=data.get("desc") or "", create_time=datetime.now())
    db.add(project)
    db.commit()
    db.refresh(project)
    invalidate("projects")
    return serialize(project)


@router.put("/api/projects/{project_id}")
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    project = get_or_404(db, Project, project_id)
    data = normalize_project_payload(schema_data(payload, exclude_unset=True))
    for field in ["name", "desc"]:
        if field in data:
            setattr(project, field, data[field])
    db.commit()
    db.refresh(project)
    invalidate("projects")
    return serialize(project)


@router.delete("/api/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    project = get_or_404(db, Project, project_id)
    task_ids = [row[0] for row in db.query(FunctionalTask.id).filter(FunctionalTask.project_id == project_id).all()]
    functional_case_rows = (
        db.query(FunctionalCase.id, FunctionalCase.ui_case_id)
        .filter(FunctionalCase.task_id.in_(task_ids))
        .all()
        if task_ids
        else []
    )
    functional_case_ids = [row[0] for row in functional_case_rows]
    generated_ui_ids = [row[1] for row in functional_case_rows if row[1]]
    direct_ui_ids = [row[0] for row in db.query(UiCase.id).filter(UiCase.project_id == project_id).all()]
    ui_ids = sorted(set(direct_ui_ids + generated_ui_ids))
    api_ids = [row[0] for row in db.query(ApiCase.id).filter(ApiCase.project_id == project_id).all()]
    profile_ids = [row[0] for row in db.query(TestAccountProfile.id).filter(TestAccountProfile.project_id == project_id).all()]

    record_filters = [TestRecord.project_id == project_id]
    if api_ids:
        record_filters.append((TestRecord.case_type == "api") & TestRecord.case_id.in_(api_ids))
    if ui_ids:
        record_filters.append((TestRecord.case_type == "ui") & TestRecord.case_id.in_(ui_ids))
    record_count = db.query(TestRecord.id).filter(or_(*record_filters)).count()
    if record_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"该项目存在 {record_count} 条执行记录，请先导出或迁移报告后再删除项目",
        )

    if api_ids:
        db.query(TestRecord).filter(TestRecord.case_type == "api", TestRecord.case_id.in_(api_ids)).delete(synchronize_session=False)
    if ui_ids:
        db.query(TestRecord).filter(TestRecord.case_type == "ui", TestRecord.case_id.in_(ui_ids)).delete(synchronize_session=False)
        db.query(LocatorHealLog).filter(LocatorHealLog.case_id.in_(ui_ids)).delete(synchronize_session=False)

    binding_filters = [
        (TestAccountBinding.target_type == "project") & (TestAccountBinding.target_id == project_id),
    ]
    if task_ids:
        binding_filters.append((TestAccountBinding.target_type == "functional_task") & TestAccountBinding.target_id.in_(task_ids))
    if functional_case_ids:
        binding_filters.append((TestAccountBinding.target_type == "functional_case") & TestAccountBinding.target_id.in_(functional_case_ids))
    if ui_ids:
        binding_filters.append((TestAccountBinding.target_type == "ui_case") & TestAccountBinding.target_id.in_(ui_ids))
    if profile_ids:
        db.query(TestAccountBinding).filter(TestAccountBinding.account_profile_id.in_(profile_ids)).delete(synchronize_session=False)
    db.query(TestAccountBinding).filter(or_(*binding_filters)).delete(synchronize_session=False)

    if task_ids:
        db.query(PageSnapshot).filter(PageSnapshot.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalScreenshot).filter(FunctionalScreenshot.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalRequirementNote).filter(FunctionalRequirementNote.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalRun).filter(FunctionalRun.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalImpactItem).filter(FunctionalImpactItem.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalDataCheckResult).filter(FunctionalDataCheckResult.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalDataCheckRule).filter(FunctionalDataCheckRule.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalCase).filter(FunctionalCase.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalTask).filter(FunctionalTask.id.in_(task_ids)).delete(synchronize_session=False)
    cg_task_ids = [row[0] for row in db.query(CaseGenerationTask.id).filter(CaseGenerationTask.project_id == project_id).all()]
    if cg_task_ids:
        db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id.in_(cg_task_ids)).delete(synchronize_session=False)
        db.query(CaseGenerationScreenshot).filter(CaseGenerationScreenshot.task_id.in_(cg_task_ids)).delete(synchronize_session=False)
        db.query(CaseGenerationRequirementNote).filter(CaseGenerationRequirementNote.task_id.in_(cg_task_ids)).delete(synchronize_session=False)
        db.query(CaseGenerationTask).filter(CaseGenerationTask.id.in_(cg_task_ids)).delete(synchronize_session=False)
    verification_task_ids = [
        row[0]
        for row in db.query(RequirementVerification.id)
        .filter(RequirementVerification.project_id == project_id)
        .all()
    ]
    if verification_task_ids:
        verification_run_ids = [
            row[0]
            for row in db.query(VerificationRun.id)
            .filter(VerificationRun.task_id.in_(verification_task_ids))
            .all()
        ]
        if verification_run_ids:
            db.query(VerificationRunItem).filter(VerificationRunItem.run_id.in_(verification_run_ids)).delete(synchronize_session=False)
            db.query(VerificationRunDataset).filter(VerificationRunDataset.run_id.in_(verification_run_ids)).delete(synchronize_session=False)
            db.query(VerificationRun).filter(VerificationRun.id.in_(verification_run_ids)).delete(synchronize_session=False)
        learning_ids = [row[0] for row in db.query(VerificationLearningSession.id).filter(VerificationLearningSession.task_id.in_(verification_task_ids)).all()]
        if learning_ids:
            db.query(VerificationLearningEvent).filter(VerificationLearningEvent.session_id.in_(learning_ids)).delete(synchronize_session=False)
            db.query(VerificationLearningSession).filter(VerificationLearningSession.id.in_(learning_ids)).delete(synchronize_session=False)
        db.query(VerificationClarification).filter(VerificationClarification.task_id.in_(verification_task_ids)).delete(synchronize_session=False)
        db.query(VerificationItem).filter(VerificationItem.task_id.in_(verification_task_ids)).delete(synchronize_session=False)
        db.query(VerificationMaterial).filter(VerificationMaterial.task_id.in_(verification_task_ids)).delete(synchronize_session=False)
        db.query(VerificationFormula).filter(VerificationFormula.task_id.in_(verification_task_ids)).delete(synchronize_session=False)
        db.query(RequirementVerification).filter(RequirementVerification.id.in_(verification_task_ids)).delete(synchronize_session=False)
    db.query(VerificationMemory).filter(VerificationMemory.project_id == project_id).delete(synchronize_session=False)
    db.query(VerificationDataSource).filter(VerificationDataSource.project_id == project_id).delete(synchronize_session=False)
    db.query(VerificationFormula).filter(VerificationFormula.project_id == project_id).delete(synchronize_session=False)
    if ui_ids:
        db.query(UiCaseRevision).filter(UiCaseRevision.case_id.in_(ui_ids)).delete(synchronize_session=False)
    db.query(UiRecordPreflight).filter(UiRecordPreflight.project_id == project_id).delete(synchronize_session=False)
    db.query(UiRecordProjectConfig).filter(UiRecordProjectConfig.project_id == project_id).delete(synchronize_session=False)
    db.query(UiLocatorMemory).filter(UiLocatorMemory.project_id == project_id).delete(synchronize_session=False)
    if ui_ids:
        db.query(UiCase).filter(UiCase.id.in_(ui_ids)).delete(synchronize_session=False)
    if api_ids:
        db.query(ApiCase).filter(ApiCase.id.in_(api_ids)).delete(synchronize_session=False)
    if profile_ids:
        db.query(TestAccountProfile).filter(TestAccountProfile.id.in_(profile_ids)).delete(synchronize_session=False)

    # 清理所有项目下的测试记录（含 case_id=0 的数据脚本记录）
    db.query(TestRecord).filter(TestRecord.project_id == project_id).delete(synchronize_session=False)

    db.query(Env).filter(Env.project_id == project_id).delete(synchronize_session=False)
    db.query(ActionTemplate).filter(ActionTemplate.project_id == project_id).delete(synchronize_session=False)
    db.delete(project)
    db.commit()
    invalidate("projects")
    return {"message": "deleted"}
