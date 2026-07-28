from fastapi import FastAPI

from .action_templates import router as action_templates_router
from .ai_config import router as ai_config_router
from .api_cases import router as api_cases_router
from .api_harvester import router as api_harvester_router
from .auth import router as auth_router
from .browser_record import router as browser_record_router
from .case_generation import router as case_generation_router
from .dashboard import router as dashboard_router
from .data_scripts import router as data_scripts_router
from .data_factory_agent import router as data_factory_agent_router
from .envs import router as envs_router
from .flow_recorder import router as flow_recorder_router
from .functional_tasks import router as functional_tasks_router
from .locator_heal_logs import router as locator_heal_logs_router
from .projects import router as projects_router
from .proxy import router as proxy_router
from .requirement_verifications import router as requirement_verifications_router
from .test_accounts import router as test_accounts_router
from .test_records import router as test_records_router
from .ui_cases import router as ui_cases_router
from .ui_record import router as ui_record_router
from .users import router as users_router


def register_routers(app: FastAPI) -> None:
    for router in (
        requirement_verifications_router,
        functional_tasks_router,
        case_generation_router,
        data_scripts_router,
        data_factory_agent_router,
        auth_router,
        dashboard_router,
        users_router,
        projects_router,
        envs_router,
        api_cases_router,
        api_harvester_router,
        ui_cases_router,
        test_accounts_router,
        action_templates_router,
        locator_heal_logs_router,
        ai_config_router,
        proxy_router,
        test_records_router,
        flow_recorder_router,
        browser_record_router,
        ui_record_router,
    ):
        app.include_router(router)
