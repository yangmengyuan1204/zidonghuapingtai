(function () {
  async function refreshRecordList(result) {
    if (typeof window.refreshTestRecordList === "function") {
      return window.refreshTestRecordList({ expectedId: result?.id, attempts: 5, delayMs: 450 });
    }
    if (typeof window.renderRecords === "function") await window.renderRecords();
    return false;
  }

  async function open(recordId) {
    try {
      const context = await window.api(`/api/test-records/${recordId}/re-execute`);
      if (!context?.available) {
        window.showToast(context?.message || "该记录缺少完整参数，请从原入口执行");
        return;
      }

      if (context.kind === "data_script") {
        const flows = typeof window.readFlows === "function" ? window.readFlows() : [];
        const candidates = flows.filter((item) => item.scriptType === context.script_key);
        const flowById = context.script_flow_id
          ? candidates.find((item) => String(item.id) === String(context.script_flow_id))
          : null;
        const flowByName = context.script_name
          ? candidates.filter((item) => String(item.name || "").trim() === String(context.script_name).trim())
          : [];
        const legacyAmbiguousFullFlow = context.script_key === "full_flow"
          && context.script_name_source !== "flow_metadata"
          && candidates.length > 1;
        const flow = flowById || (!legacyAmbiguousFullFlow && flowByName.length === 1 ? flowByName[0] : null);
        if (!flow || typeof window.openRunScriptForm !== "function") {
          window.showToast(
            legacyAmbiguousFullFlow
              ? "历史记录缺少明确脚本身份，请到数据工厂选择对应脚本执行"
              : "未找到对应数据脚本入口，请到数据工厂中执行",
          );
          return;
        }
        const defaults = typeof window.safeVariables === "function" ? window.safeVariables(flow.variables) : {};
        const prepared = {
          ...flow,
          variables: JSON.stringify({
            ...defaults,
            ...(context.variables || {}),
            _data_script_flow_id: flow.id,
            _data_script_name: flow.name,
          }),
        };
        window.openRunScriptForm(prepared);
        window.showToast(
          context.sensitive_keys?.length
            ? `已回填原参数，敏感参数 ${context.sensitive_keys.join("、")} 需要重新确认`
            : "已回填原参数，请核对后执行",
        );
        return;
      }

      const sensitiveHint = context.sensitive_keys?.length
        ? `\n敏感参数：${context.sensitive_keys.join("、")}（已加密保存）`
        : "";
      if (!window.confirm(`确认再次执行记录 #${recordId}？${sensitiveHint}`)) return;

      const progress = typeof window.openScriptProgress === "function"
        ? window.openScriptProgress("再次执行", "正在重新执行，请稍候...")
        : null;
      progress?.update(30, "正在执行...");
      const result = await window.api(`/api/test-records/${recordId}/re-execute`, {
        method: "POST",
        body: { confirmed: true },
      });
      progress?.update(92, "正在刷新执行报告...");
      await refreshRecordList(result);
      progress?.success("执行完成，列表已刷新");
      window.showToast(`执行完成：${result.result === "passed" ? "成功" : "失败"}`);
    } catch (error) {
      window.showToast(error.message || "再次执行失败");
    }
  }

  window.TestRecordRerun = { open };
})();
