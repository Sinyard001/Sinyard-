/* 智能合同工作台前端逻辑 */
"use strict";

(function () {
  const $ = function (selector) {
    return document.querySelector(selector);
  };

  const els = {
    title: $("#title"),
    text: $("#contractText"),
    runBtn: $("#runBtn"),
    clearBtn: $("#clearBtn"),
    demoBtn: $("#demoBtn"),
    fileInput: $("#fileInput"),
    resetBtn: $("#resetBtn"),
    status: $("#statusText"),
    report: $("#report"),
    reportMeta: $("#reportMeta"),
    statClauses: $("#statClauses"),
    statHigh: $("#statHigh"),
    statMedium: $("#statMedium"),
    statLow: $("#statLow"),
    statGrade: $("#statGrade"),
    clausesTab: $("#clausesTab"),
    risksTab: $("#risksTab"),
    entitiesTab: $("#entitiesTab"),
    gapsTab: $("#gapsTab"),
    stanceSummary: $("#stanceSummary"),
    riskList: $("#riskList"),
    entityTable: $("#entityTable"),
    paymentPlan: $("#paymentPlan"),
    gapList: $("#gapList"),
    saveLedgerBtn: $("#saveLedgerBtn"),
    saveLedgerStatus: $("#saveLedgerStatus"),
    qaContext: $("#qaContext"),
    chatLog: $("#chatLog"),
    qaInput: $("#qaInput"),
    qaSendBtn: $("#qaSendBtn"),
    oldText: $("#oldText"),
    newText: $("#newText"),
    oldDemoBtn: $("#oldDemoBtn"),
    newDemoBtn: $("#newDemoBtn"),
    useCurrentAsOld: $("#useCurrentAsOld"),
    compareBtn: $("#compareBtn"),
    compareStatus: $("#compareStatus"),
    compareResult: $("#compareResult"),
    exportLedgerBtn: $("#exportLedgerBtn"),
    clearLedgerBtn: $("#clearLedgerBtn"),
    ledgerBody: $("#ledgerBody"),
    ledgerStatus: $("#ledgerStatus"),
  };

  const state = {
    currentText: "",
    currentTitle: "",
    currentResult: null,
  };

  const LEDGER_KEY = "contractLedger_v1";

  /* ---------- 通用 ---------- */
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function setStatus(el, message, type) {
    el.textContent = message || "";
    el.className = "status-text" + (type ? " " + type : "");
  }

  function severityText(severity) {
    if (severity === "high") return "高风险";
    if (severity === "medium") return "中风险";
    return "提示";
  }

  function valueOrNot(value) {
    if (value == null) return "未识别";
    const text = String(value).trim();
    return text || "未识别";
  }

  function isValidContract(text) {
    return text && text.replace(/\s/g, "").length >= 20;
  }

  function hasLoadedContract() {
    if (isValidContract(state.currentText)) return true;
    setStatus(els.status, "请先在“审查工作台”粘贴合同正文，或点击“载入演示合同”。", "error");
    switchSection("review");
    return false;
  }

  /* ---------- 顶部工作区切换 ---------- */
  function switchSection(sectionName) {
    document.querySelectorAll(".work-section").forEach(function (section) {
      section.classList.add("hidden");
    });
    const target = document.getElementById("section-" + sectionName);
    if (target) target.classList.remove("hidden");
    document.querySelectorAll(".main-tab").forEach(function (tab) {
      tab.classList.toggle("active", tab.dataset.section === sectionName);
    });
  }

  document.querySelectorAll(".main-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      switchSection(tab.dataset.section);
    });
  });

  document.querySelectorAll(".sub-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".sub-tab").forEach(function (item) {
        item.classList.toggle("active", item === tab);
      });
      document.querySelectorAll(".report-tab").forEach(function (panel) {
        panel.classList.add("hidden");
      });
      const target = document.getElementById(tab.dataset.reportTab);
      if (target) target.classList.remove("hidden");
    });
  });

  /* ---------- 审查流程 ---------- */
  function setBusy(busy) {
    els.runBtn.disabled = busy;
    els.demoBtn.disabled = busy;
    els.fileInput.disabled = busy;
    els.runBtn.textContent = busy ? "正在审查……" : "开始智能审查";
  }

  async function requestAnalyze(payload) {
    setBusy(true);
    setStatus(els.status, "正在审查合同并提取要素，请稍候……（首次运行需加载模型，约 10 秒）", "loading");
    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!data.ok) {
        throw new Error(data.error || "审查失败，请重试。");
      }
      state.currentResult = data.result;
      state.currentTitle = data.result.title || state.currentTitle;
      showReport(data.result);
      setStatus(els.status, "审查完成。", "");
    } catch (error) {
      setStatus(els.status, error.message || "审查失败，请重试。", "error");
    } finally {
      setBusy(false);
    }
  }

  async function loadDemo() {
    setBusy(true);
    setStatus(els.status, "正在载入演示合同……", "loading");
    try {
      const response = await fetch("/api/sample");
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "载入失败");
      els.title.value = data.title || "";
      els.text.value = data.text || "";
      state.currentText = data.text || "";
      state.currentTitle = data.title || "";
      state.currentResult = null;
      els.report.classList.add("hidden");
      setStatus(els.status, "演示合同已载入，点击“开始智能审查”查看完整工作台结果。", "");
      updateQaContext();
    } catch (error) {
      setStatus(els.status, error.message || "载入演示合同失败。", "error");
    } finally {
      setBusy(false);
    }
  }

  function startReview() {
    const text = els.text.value || "";
    if (!isValidContract(text)) {
      setStatus(els.status, "请先粘贴合同正文，或点击“载入演示合同”。", "error");
      els.text.focus();
      return;
    }
    state.currentText = text;
    state.currentTitle = els.title.value || "";
    requestAnalyze({ title: els.title.value || "", text: text });
  }

  function resetAll() {
    els.title.value = "";
    els.text.value = "";
    els.report.classList.add("hidden");
    state.currentText = "";
    state.currentTitle = "";
    state.currentResult = null;
    setStatus(els.status, "", "");
    updateQaContext();
    els.text.focus();
  }

  async function handleFile(file) {
    if (!file) return;
    if (!/\.(txt|docx)$/i.test(file.name)) {
      setStatus(els.status, "仅支持 .txt 或 .docx 合同文件。", "error");
      return;
    }
    setBusy(true);
    setStatus(els.status, "正在读取并审查文件……（.docx 首次审查约 10 秒）", "loading");
    try {
      const base64 = await readFileAsBase64(file);
      const response = await fetch("/api/review-upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          title: file.name.replace(/\.(txt|docx)$/i, ""),
          content: base64,
        }),
      });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "文件审查失败。");
      const result = data.result;
      state.currentResult = result;
      state.currentText = result.text || "";
      state.currentTitle = result.title || file.name;
      els.title.value = state.currentTitle;
      els.text.value = "";
      showReport(result);
      setStatus(els.status, "文件审查完成，已自动提取台账要素。", "");
      updateQaContext();
    } catch (error) {
      setStatus(els.status, error.message || "文件审查失败。", "error");
    } finally {
      setBusy(false);
      els.fileInput.value = "";
    }
  }

  function readFileAsBase64(file) {
    return new Promise(function (resolve, reject) {
      const reader = new FileReader();
      reader.onload = function () {
        const raw = String(reader.result || "");
        const index = raw.indexOf(",");
        resolve(index >= 0 ? raw.slice(index + 1) : raw);
      };
      reader.onerror = function () {
        reject(new Error("文件读取失败，请重试。"));
      };
      reader.readAsDataURL(file);
    });
  }

  /* ---------- 报告渲染 ---------- */
  function showReport(result) {
    const summary = result.summary || {};
    const risks = summary.risks || {};
    const grading = (result.stances || {}).grading || { level: "-", score: 0 };
    els.statClauses.textContent = String(summary.clause_count || 0);
    els.statHigh.textContent = String(risks.high || 0);
    els.statMedium.textContent = String(risks.medium || 0);
    els.statLow.textContent = String(risks.low || 0);
    els.statGrade.textContent = grading.level || "低";
    els.statGrade.style.color = grading.level === "高" ? "#d21f26" : "#000";
    els.reportMeta.textContent =
      "合同名称：" + (result.title || "未命名合同") +
      " · 综合风险指数 " + (grading.score || 0) + "/100 · " +
      ((grading.comment || "") || "请逐项复核");
    renderClauses(result.clauses || []);
    renderRisksAndStances(result);
    renderEntities(result);
    renderGaps(result.gap_suggestions || []);
    showReportTab("clausesTab");
    els.report.classList.remove("hidden");
    els.report.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function showReportTab(tabName) {
    document.querySelectorAll(".sub-tab").forEach(function (tab) {
      tab.classList.toggle("active", tab.dataset.reportTab === tabName);
    });
    document.querySelectorAll(".report-tab").forEach(function (panel) {
      panel.classList.add("hidden");
    });
    const target = document.getElementById(tabName);
    if (target) target.classList.remove("hidden");
  }

  function renderClauses(clauses) {
    if (!clauses.length) {
      els.clausesTab.innerHTML =
        '<div class="empty-note">未能从文本中识别出带编号的条款，请检查合同格式。</div>';
      return;
    }
    els.clausesTab.innerHTML = clauses.map(function (clause) {
      const confidence =
        typeof clause.confidence === "number"
          ? "置信度 " + Math.round(clause.confidence * 100) + "%"
          : "";
      const hasRisks = Array.isArray(clause.risks) && clause.risks.length > 0;
      const riskMarks = hasRisks
        ? '<div class="clause-risk-marks">' +
          clause.risks
            .map(function (risk) {
              return '<span class="risk-mark">● ' + escapeHtml(risk.title) + "</span>";
            })
            .join("") +
          "</div>"
        : "";
      return (
        '<article class="clause-card' + (hasRisks ? " is-key" : "") + '">' +
        '<div class="clause-top">' +
        '<span class="clause-number">' + escapeHtml(clause.number) + "</span>" +
        '<span class="label-tag">' + escapeHtml(clause.label || "未分类") + "</span>" +
        (confidence ? '<span class="confidence">' + confidence + "</span>" : "") +
        "</div>" +
        '<div class="clause-text">' + escapeHtml(clause.text) + "</div>" +
        riskMarks +
        "</article>"
      );
    }).join("");
  }

  function renderRisksAndStances(result) {
    const stances = result.stances || {};
    const findings = result.risks || [];
    const matrix = stances.matrix || [];
    const grading = stances.grading || {};

    const aSummary = stances.a_summary || {};
    const bSummary = stances.b_summary || {};
    els.stanceSummary.innerHTML =
      '<div class="stance-cards">' +
      '<div class="stance-card">' +
      '<div class="stance-party">' + escapeHtml(stances.party_a || "甲方") + " 视角</div>" +
      '<div class="stance-counts">高 ' + (aSummary.high || 0) +
      " · 中 " + (aSummary.medium || 0) + " · 提示 " + (aSummary.low || 0) + "</div>" +
      "</div>" +
      '<div class="stance-card">' +
      '<div class="stance-party">' + escapeHtml(stances.party_b || "乙方") + " 视角</div>" +
      '<div class="stance-counts">高 ' + (bSummary.high || 0) +
      " · 中 " + (bSummary.medium || 0) + " · 提示 " + (bSummary.low || 0) + "</div>" +
      "</div>" +
      '<div class="stance-card stance-note">' +
      '<div class="stance-party">综合等级 ' + escapeHtml(grading.level || "-") +
      " · 指数 " + (grading.score || 0) + "/100</div>" +
      '<div class="stance-counts">' + escapeHtml(grading.comment || "") + "</div>" +
      "</div></div>" +
      '<p class="stance-note-text">' + escapeHtml(stances.note || "") + "</p>";

    if (!matrix.length) {
      els.riskList.innerHTML =
        '<div class="empty-note">当前规则未发现风险项；若矩阵为空，请在添加风险规则后重新审查。</div>';
      return;
    }

    const matrixHtml =
      '<h4 class="sub-title">多立场风险矩阵</h4>' +
      '<div class="matrix-wrap"><table class="matrix-table">' +
      "<thead><tr><th>风险</th><th>等级</th><th>位置</th>" +
      "<th>" + escapeHtml(stances.party_a || "甲方") + " 视角</th>" +
      "<th>" + escapeHtml(stances.party_b || "乙方") + " 视角</th>" +
      "<th>审查要点</th></tr></thead><tbody>" +
      matrix
        .map(function (item) {
          return (
            "<tr><td>" + escapeHtml(item.title) + "</td>" +
            '<td class="' + item.severity + '-cell">' + severityText(item.severity) + "</td>" +
            "<td>" + escapeHtml(item.clause_number || "整份合同") + "</td>" +
            "<td>" + escapeHtml(item.party_a_impact || "需关注") + "</td>" +
            "<td>" + escapeHtml(item.party_b_impact || "需关注") + "</td>" +
            "<td>" + escapeHtml(item.explanation) + "</td></tr>"
          );
        })
        .join("") +
      "</tbody></table></div>";

    const riskCards =
      '<h4 class="sub-title">风险清单与建议</h4>' +
      findings
        .slice()
        .sort(function (a, b) {
          const order = { high: 0, medium: 1, low: 2 };
          return (order[a.severity] || 3) - (order[b.severity] || 3);
        })
        .map(function (finding) {
          const position = finding.clause_number || "整份合同";
          const stance = matrix.find(function (item) {
            return item.code === finding.code;
          });
          return (
            '<article class="risk-card severity-' + finding.severity + '">' +
            '<div class="risk-head"><span class="risk-title">' + escapeHtml(finding.title) +
            '</span><span class="risk-severity">' + severityText(finding.severity) + "</span></div>" +
            '<div class="risk-meta">' + escapeHtml(position) +
            (stance && stance.adverse_party ? " · 不利方：" + escapeHtml(stance.adverse_party) : "") +
            " · " + escapeHtml(finding.code) + "</div>" +
            '<p class="risk-message">' + escapeHtml(finding.message) + "</p>" +
            '<p class="risk-suggestion">' + escapeHtml(finding.suggestion) + "</p>" +
            "</article>"
          );
        })
        .join("");
    els.riskList.innerHTML = matrixHtml + riskCards;
  }

  function renderEntities(result) {
    const entities = result.entities || {};
    const ledger = entities.ledger || [];
    const rows = ledger
      .map(function (row) {
        if (!Array.isArray(row) || row.length < 2) return "";
        return (
          "<tr><th>" + escapeHtml(row[0]) + "</th><td>" + escapeHtml(row[1]) + "</td></tr>"
        );
      })
      .join("");
    els.entityTable.innerHTML =
      '<h4 class="sub-title">台账要素（自动提取）</h4>' +
      '<div class="entity-table-wrap"><table class="ledger-table"><tbody>' + rows + "</tbody></table></div>";

    const dates = entities.dates || [];
    if (dates.length) {
      els.entityTable.innerHTML +=
        '<h4 class="sub-title">识别到的日期</h4><ul class="simple-list">' +
        dates
          .map(function (item) {
            return "<li>" + escapeHtml(item.label) + "：" + escapeHtml(item.date) +
              "（" + escapeHtml(item.snippet) + "）</li>";
          })
          .join("") +
        "</ul>";
    }

    const plan = entities.payment_plan || [];
    if (plan.length) {
      els.paymentPlan.innerHTML =
        '<h4 class="sub-title">付款计划提取</h4><ul class="payment-plan">' +
        plan
          .map(function (item) {
            return (
              "<li><strong>" + escapeHtml(item.stage) + "</strong>" +
              (item.ratio ? "，占比 " + escapeHtml(item.ratio) : "") +
              (item.deadline ? "，期限：" + escapeHtml(item.deadline) : "") +
              "<div class=\"payment-condition\">" + escapeHtml(item.condition) + "</div></li>"
            );
          })
          .join("") +
        "</ul>";
    } else {
      els.paymentPlan.innerHTML = "";
    }
  }

  function renderGaps(gaps) {
    if (!gaps.length) {
      els.gapList.innerHTML =
        '<div class="empty-note">核心条款已基本齐备，未发现明显缺项；仍建议结合交易类型核对。</div>';
      return;
    }
    els.gapList.innerHTML = gaps
      .map(function (gap) {
        const urgencyClass = gap.urgency === "高" ? "urgency-high" : "urgency-medium";
        return (
          '<article class="gap-card">' +
          '<div class="gap-head"><strong>' + escapeHtml(gap.category) +
          '</strong><span class="urgency ' + urgencyClass + '">建议补齐 · ' +
          escapeHtml(gap.urgency) + "优先级</span></div>" +
          '<p class="gap-reason">' + escapeHtml(gap.reason) + "</p>" +
          '<div class="gap-text">' + escapeHtml(gap.suggested_text) + "</div>" +
          '<div class="gap-actions">' +
          '<button class="btn btn-outline small gap-copy" data-text="' +
          escapeHtml(gap.suggested_text) + '">复制拟补条款</button>' +
          '<span class="status-text gap-status"></span>' +
          "</div>" +
          '<p class="gap-note">' + escapeHtml(gap.note || "") + "</p>" +
          "</article>"
        );
      })
      .join("");
    document.querySelectorAll(".gap-copy").forEach(function (button) {
      button.addEventListener("click", function () {
        copyText(button.dataset.text, button.parentElement.querySelector(".gap-status"));
      });
    });
  }

  function copyText(text, statusEl) {
    const done = function () {
      setStatus(statusEl, "已复制。", "");
      setTimeout(function () {
        setStatus(statusEl, "", "");
      }, 1800);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () {
        fallbackCopy(text);
        done();
      });
    } else {
      fallbackCopy(text);
      done();
    }
  }

  function fallbackCopy(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
    } catch (error) {
      // 忽略复制失败
    }
    document.body.removeChild(area);
  }

  /* ---------- 智能问答 ---------- */
  function updateQaContext() {
    if (isValidContract(state.currentText)) {
      els.qaContext.textContent =
        "当前问答对象：" + (state.currentTitle || "未命名合同") +
        "（" + state.currentText.replace(/\s/g, "").length + " 字）";
      els.qaContext.classList.remove("muted");
    } else {
      els.qaContext.textContent = "尚未载入合同，请先在“审查工作台”粘贴或上传合同。";
      els.qaContext.classList.add("muted");
    }
  }

  function appendChat(role, html) {
    const wrap = document.createElement("div");
    wrap.className = "chat-msg " + (role === "user" ? "user" : "assistant");
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.innerHTML = html;
    wrap.appendChild(bubble);
    els.chatLog.appendChild(wrap);
    els.chatLog.scrollTop = els.chatLog.scrollHeight;
  }

  function answerHtml(answer) {
    const safe = escapeHtml(answer);
    const withBullets = safe.replace(/\n/g, "<br>");
    return withBullets.replace(/- /g, "• ");
  }

  async function askQuestion(question) {
    if (!hasLoadedContract()) return;
    if (!question.trim()) return;
    appendChat("user", escapeHtml(question));
    const sendBtn = els.qaSendBtn;
    sendBtn.disabled = true;
    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question,
          title: state.currentTitle || "",
          text: state.currentText,
        }),
      });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "问答失败");
      const answer = data.result.answer || "暂无回答。";
      let html = '<div class="qa-answer-text">' + answerHtml(answer) + "</div>";
      const references = data.result.references || [];
      if (references.length) {
        html += '<div class="qa-refs"><strong>引用条款</strong>' +
          references
            .map(function (ref) {
              const risk = (ref.risks && ref.risks.length)
                ? "<div class=\"muted\">提示：" + escapeHtml(ref.risks.join("；")) + "</div>"
                : "";
              return (
                '<div class="qa-ref">' +
                "<span class=\"label-tag\">" + escapeHtml(ref.label || "条款") + "</span> " +
                escapeHtml(ref.number || "") + "：" + escapeHtml(ref.text || "") + risk +
                "</div>"
              );
            })
            .join("") +
          "</div>";
      }
      appendChat("assistant", html);
    } catch (error) {
      appendChat("assistant", escapeHtml(error.message || "问答失败，请重试。"));
    } finally {
      sendBtn.disabled = false;
      els.qaInput.focus();
    }
  }

  /* ---------- 版本比对 ---------- */
  async function loadCompareText(target, endpoint) {
    const statusEl = target === "old" ? els.oldText : els.newText;
    const box = target === "old" ? els.oldText : els.newText;
    setStatus(els.compareStatus, "正在载入……", "loading");
    try {
      const response = await fetch(endpoint);
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "载入失败");
      box.value = data.text || "";
      setStatus(els.compareStatus, data.title + " 已载入，点击“开始比对”。", "");
    } catch (error) {
      setStatus(els.compareStatus, error.message, "error");
    }
  }

  async function runCompare() {
    const oldText = els.oldText.value || "";
    const newText = els.newText.value || "";
    if (!isValidContract(oldText) || !isValidContract(newText)) {
      setStatus(els.compareStatus, "请同时提供旧版与新版合同文本（可点击演示按钮）。", "error");
      return;
    }
    setStatus(els.compareStatus, "正在比对，请稍候……", "loading");
    els.compareBtn.disabled = true;
    try {
      const response = await fetch("/api/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          old_text: oldText,
          new_text: newText,
          old_title: "旧版合同",
          new_title: "新版合同",
        }),
      });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "比对失败");
      renderCompare(data.result);
      setStatus(els.compareStatus, "比对完成。", "");
    } catch (error) {
      setStatus(els.compareStatus, error.message || "比对失败。", "error");
    } finally {
      els.compareBtn.disabled = false;
    }
  }

  function renderCompare(result) {
    const summary = result.summary || {};
    const risk = result.risk_delta || {};
    const stats =
      '<div class="stats-row compare-stats">' +
      '<div class="stat-card"><span class="stat-value">' + (summary.old_clauses || 0) +
      '</span><span class="stat-label">旧版条款</span></div>' +
      '<div class="stat-card"><span class="stat-value">' + (summary.new_clauses || 0) +
      '</span><span class="stat-label">新版条款</span></div>' +
      '<div class="stat-card"><span class="stat-value stat-mod">' + (summary.modified || 0) +
      '</span><span class="stat-label">修改</span></div>' +
      '<div class="stat-card stat-danger"><span class="stat-value">' + (summary.added || 0) +
      '</span><span class="stat-label">新增</span></div>' +
      '<div class="stat-card"><span class="stat-value">' + (summary.removed || 0) +
      '</span><span class="stat-label">删除</span></div>' +
      "</div>";

    const riskDelta = renderRiskDelta(risk);
    const diffItems = (result.items || [])
      .filter(function (item) {
        return item.kind !== "unchanged";
      })
      .map(function (item) {
        let badge = "修改";
        if (item.kind === "added") badge = "新增";
        if (item.kind === "removed") badge = "删除";
        const oldLabel = item.old_label ? "【" + item.old_label + "】" : "";
        const newLabel = item.new_label ? "【" + item.new_label + "】" : "";
        let diffHtml = "";
        if (item.kind === "modified") {
          diffHtml = renderDiffChunks(item.chunks || []);
          if (item.label_changed) {
            diffHtml += '<div class="diff-label-note">条款类型变化：' +
              escapeHtml(oldLabel || "无") + " → " + escapeHtml(newLabel || "无") + "</div>";
          }
        } else {
          diffHtml = '<div class="' + (item.kind === "added" ? "diff-ins-block" : "diff-del-block") + '">' +
            escapeHtml(item.new_text || item.old_text) + "</div>";
        }
        return (
          '<article class="diff-card kind-' + item.kind + '">' +
          '<div class="diff-head"><strong>' + escapeHtml(item.number) +
          "</strong><span class=\"label-tag\">" + badge + "</span>" +
          '<span class="confidence">相似度 ' + Math.round((item.similarity || 0) * 100) + "%</span></div>" +
          diffHtml +
          "</article>"
        );
      })
      .join("");

    els.compareResult.innerHTML =
      "<h3 class=\"section-head\">比对结果</h3>" +
      stats +
      riskDelta +
      '<h4 class="sub-title">条款差异（未变化 ' + (summary.unchanged || 0) + " 条）</h4>" +
      (diffItems || '<div class="empty-note">条款内容没有发现差异。</div>') +
      '<p class="muted">' + escapeHtml(result.note || "") + "</p>";
    els.compareResult.classList.remove("hidden");
    els.compareResult.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderRiskDelta(risk) {
    const oldRisks = risk.old_summary || {};
    const newRisks = risk.new_summary || {};
    const removed = (risk.removed || []).map(function (item) {
      return "<li><span class=\"diff-del-tag\">旧版已消除</span>" + escapeHtml(item.title) + "</li>";
    }).join("");
    const added = (risk.added || []).map(function (item) {
      return "<li><span class=\"diff-ins-tag\">新版新增</span>" + escapeHtml(item.title) + "</li>";
    }).join("");
    const kept = (risk.kept || []).map(function (item) {
      return "<li><span class=\"diff-keep-tag\">两版都有</span>" + escapeHtml(item.title) + "</li>";
    }).join("");
    return (
      '<h4 class="sub-title">风险变化</h4>' +
      '<div class="risk-delta-stats">旧版风险：高 ' + (oldRisks.high || 0) +
      " · 中 " + (oldRisks.medium || 0) + " · 提示 " + (oldRisks.low || 0) +
      "　→　新版风险：高 " + (newRisks.high || 0) +
      " · 中 " + (newRisks.medium || 0) + " · 提示 " + (newRisks.low || 0) + "</div>" +
      '<div class="risk-changes"><ul>' + removed + added + kept + "</ul></div>"
    );
  }

  function renderDiffChunks(chunks) {
    const html = chunks
      .map(function (chunk) {
        if (chunk.type === "equal") return escapeHtml(chunk.text);
        if (chunk.type === "delete") {
          return '<span class="diff-del">' + escapeHtml(chunk.old || chunk.text) + "</span>";
        }
        if (chunk.type === "insert") {
          return '<span class="diff-ins">' + escapeHtml(chunk.new || chunk.text) + "</span>";
        }
        return (
          '<span class="diff-del">' + escapeHtml(chunk.old || "") + "</span>" +
          '<span class="diff-ins">' + escapeHtml(chunk.new || "") + "</span>"
        );
      })
      .join("");
    return '<div class="diff-text">' + html + "</div>";
  }

  /* ---------- 台账 ---------- */
  function readLedger() {
    try {
      return JSON.parse(localStorage.getItem(LEDGER_KEY) || "[]");
    } catch (error) {
      return [];
    }
  }

  function writeLedger(entries) {
    localStorage.setItem(LEDGER_KEY, JSON.stringify(entries));
  }

  function fieldMap(ledgerRows) {
    const map = {};
    (ledgerRows || []).forEach(function (row) {
      if (Array.isArray(row) && row[0]) map[row[0]] = row[1];
    });
    return map;
  }

  function saveCurrentToLedger() {
    const result = state.currentResult;
    if (!result || !state.currentText) {
      setStatus(els.saveLedgerStatus, "请先完成一次审查，再保存到台账。", "error");
      return;
    }
    const entities = result.entities || {};
    const map = fieldMap(entities.ledger);
    const summary = result.summary || {};
    const grading = (result.stances || {}).grading || {};
    const entry = {
      savedAt: new Date().toISOString(),
      title: result.title || state.currentTitle || "未命名合同",
      partyA: map["甲方"] || "",
      partyB: map["乙方"] || "",
      amount: map["合同金额"] || "",
      duration: map["合同期限"] || "",
      payment: map["付款安排"] || "",
      dispute: map["争议解决"] || "",
      riskLevel: grading.level || "低",
      high: summary.risks && summary.risks.high ? summary.risks.high : 0,
      medium: summary.risks && summary.risks.medium ? summary.risks.medium : 0,
      clauses: summary.clause_count || 0,
      ledger: entities.ledger || [],
    };
    const entries = readLedger().filter(function (item) {
      return item.title !== entry.title;
    });
    entries.unshift(entry);
    writeLedger(entries);
    renderLedger();
    setStatus(els.saveLedgerStatus, "已保存《" + entry.title + "》到本地台账。", "");
    setTimeout(function () {
      setStatus(els.saveLedgerStatus, "", "");
    }, 2500);
  }

  function renderLedger() {
    const entries = readLedger();
    if (!entries.length) {
      els.ledgerBody.innerHTML =
        '<tr><td colspan="8" class="empty-cell">台账为空。完成审查后点击“保存当前合同到台账”。</td></tr>';
      return;
    }
    els.ledgerBody.innerHTML = entries
      .map(function (entry, index) {
        const date = new Date(entry.savedAt);
        const dateText =
          date.getFullYear() + "-" +
          String(date.getMonth() + 1).padStart(2, "0") + "-" +
          String(date.getDate()).padStart(2, "0") + " " +
          String(date.getHours()).padStart(2, "0") + ":" +
          String(date.getMinutes()).padStart(2, "0");
        return (
          "<tr>" +
          "<td>" + dateText + "</td>" +
          "<td class=\"strong-cell\">" + escapeHtml(entry.title) + "</td>" +
          "<td>" + escapeHtml(entry.partyA || "未识别") + "</td>" +
          "<td>" + escapeHtml(entry.partyB || "未识别") + "</td>" +
          "<td>" + escapeHtml(entry.amount || "未识别") + "</td>" +
          "<td>" + escapeHtml(entry.duration || "未识别") + "</td>" +
          "<td>" + escapeHtml(entry.riskLevel || "-") + "</td>" +
          '<td><button class="btn btn-outline small ledger-delete" data-index="' + index + '">删除</button></td>' +
          "</tr>"
        );
      })
      .join("");
    document.querySelectorAll(".ledger-delete").forEach(function (button) {
      button.addEventListener("click", function () {
        deleteLedgerEntry(Number(button.dataset.index));
      });
    });
  }

  function deleteLedgerEntry(index) {
    const entries = readLedger();
    if (index >= 0 && index < entries.length) {
      entries.splice(index, 1);
      writeLedger(entries);
      renderLedger();
      setStatus(els.ledgerStatus, "已删除一条台账记录。", "");
    }
  }

  function exportLedgerCsv() {
    const entries = readLedger();
    if (!entries.length) {
      setStatus(els.ledgerStatus, "台账为空，暂无可导出的记录。", "error");
      return;
    }
    const headers = [
      "保存时间", "合同名称", "甲方", "乙方", "合同金额", "合同期限",
      "付款安排", "争议解决", "风险等级",
    ];
    const rows = entries.map(function (entry) {
      return [
        new Date(entry.savedAt).toLocaleString(),
        entry.title,
        entry.partyA,
        entry.partyB,
        entry.amount,
        entry.duration,
        entry.payment,
        entry.dispute,
        entry.riskLevel,
      ];
    });
    const csv = "\ufeff" + [headers].concat(rows)
      .map(function (row) {
        return row.map(csvCell).join(",");
      })
      .join("\r\n");
    downloadText("合同台账.csv", csv);
    setStatus(els.ledgerStatus, "已导出 " + entries.length + " 条合同台账。", "");
  }

  function csvCell(value) {
    const text = String(value == null ? "" : value).replaceAll('"', '""');
    if (/[",\n]/.test(text)) return '"' + text + '"';
    return text;
  }

  function downloadText(filename, text) {
    const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () {
      URL.revokeObjectURL(link.href);
    }, 1000);
  }

  function clearLedger() {
    if (!readLedger().length) {
      setStatus(els.ledgerStatus, "台账本来就是空的。", "");
      return;
    }
    if (!window.confirm("确认清空本地保存的全部合同台账吗？此操作不可恢复。")) return;
    localStorage.removeItem(LEDGER_KEY);
    renderLedger();
    setStatus(els.ledgerStatus, "本地台账已清空。", "");
  }

  /* ---------- 事件绑定 ---------- */
  els.runBtn.addEventListener("click", startReview);
  els.demoBtn.addEventListener("click", loadDemo);
  els.clearBtn.addEventListener("click", function () {
    els.title.value = "";
    els.text.value = "";
    setStatus(els.status, "", "");
  });
  els.resetBtn.addEventListener("click", resetAll);
  els.fileInput.addEventListener("change", function () {
    handleFile(els.fileInput.files[0]);
  });

  els.saveLedgerBtn.addEventListener("click", saveCurrentToLedger);

  function sendQa() {
    const question = els.qaInput.value.trim();
    if (!question) return;
    els.qaInput.value = "";
    askQuestion(question);
  }
  els.qaSendBtn.addEventListener("click", sendQa);
  els.qaInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") sendQa();
  });
  document.querySelectorAll(".chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      els.qaInput.value = chip.dataset.question || "";
      sendQa();
    });
  });

  els.oldDemoBtn.addEventListener("click", function () {
    loadCompareText("old", "/api/sample");
  });
  els.newDemoBtn.addEventListener("click", function () {
    loadCompareText("new", "/api/sample-v2");
  });
  els.useCurrentAsOld.addEventListener("click", function () {
    if (!hasLoadedContract()) return;
    els.oldText.value = state.currentText;
    setStatus(els.compareStatus, "已将当前合同填入旧版 A，请再准备新版 B。", "");
  });
  els.compareBtn.addEventListener("click", runCompare);

  els.exportLedgerBtn.addEventListener("click", exportLedgerCsv);
  els.clearLedgerBtn.addEventListener("click", clearLedger);

  /* ---------- 初始化 ---------- */
  renderLedger();
  updateQaContext();
})();
