(() => {
  "use strict";

  const COLORS = { learning: "#f5c96a", engineering: "#73d9ff", agent: "#c5a4ff", personal: "#ff9dbb" };
  const CATEGORY_NAMES = { learning: "学习系统", engineering: "工程现场", agent: "AI 与工作流", personal: "重要的人" };
  const state = { data: null, activeView: "overview", category: "all", query: "", nodes: [], spark: null };
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const fallback = {
    schemaVersion: 1,
    owner: "sunccchengze",
    since: "2026-08-01T00:00:00Z",
    stats: { repositories: 0, branches: 0, recentCommits: 0, meaningfulCommits: 0, activeRepositories: 0, categories: 4 },
    categories: Object.entries(CATEGORY_NAMES).map(([id, name]) => ({ id, name, color: COLORS[id], repoCount: 0, description: "等待本地快照。" })),
    repositories: [], timeline: [], commits: [], highlights: [], narrative: [],
  };

  function formatNumber(value) { return Number(value || 0).toLocaleString("zh-CN"); }
  function shortDate(value, withYear = false) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
    return `${withYear ? `${date.getFullYear()}.` : ""}${String(date.getMonth() + 1).padStart(2, "0")}.${String(date.getDate()).padStart(2, "0")}`;
  }
  function dateLabel(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value).slice(0, 10) : `${String(date.getMonth() + 1).padStart(2, "0")}/${String(date.getDate()).padStart(2, "0")}`;
  }
  function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>'"]/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
  }
  function categoryFor(repo) { return (repo.categories && repo.categories[0]) || "personal"; }
  function colorFor(repo) { return COLORS[categoryFor(repo)] || COLORS.personal; }
  function categoryName(id) { return CATEGORY_NAMES[id] || id; }

  async function loadData() {
    let response;
    try { response = await fetch("data/generated.json", { cache: "no-store" }); if (!response.ok) throw new Error("generated unavailable"); return await response.json(); }
    catch (_) {
      try { response = await fetch("demo.json", { cache: "no-store" }); if (!response.ok) throw new Error("demo unavailable"); return await response.json(); }
      catch (_) { return fallback; }
    }
  }

  function renderStats() {
    const stats = state.data.stats || {};
    [["#metric-repos", stats.repositories], ["#metric-branches", stats.branches], ["#metric-commits", stats.meaningfulCommits ?? stats.recentCommits], ["#metric-active", stats.activeRepositories]].forEach(([selector, value]) => { const node = $(selector); if (node) node.textContent = formatNumber(value); });
    const activity = $("#activity-big"); if (activity) activity.textContent = formatNumber(stats.meaningfulCommits ?? stats.recentCommits);
    const total = $("#timeline-total"); if (total) total.textContent = formatNumber(stats.meaningfulCommits ?? stats.recentCommits);
  }

  function renderLegend() {
    const legend = $("#category-legend");
    if (!legend) return;
    legend.innerHTML = (state.data.categories || []).map(category => `<button class="legend-item" data-category-filter="${escapeHTML(category.id)}"><span class="legend-dot" style="background:${category.color || COLORS[category.id]}"></span><span>${escapeHTML(category.name)}</span><b>${formatNumber(category.repoCount)}</b></button>`).join("");
    $$("[data-category-filter]", legend).forEach(button => button.addEventListener("click", () => { state.category = state.category === button.dataset.categoryFilter ? "all" : button.dataset.categoryFilter; renderProjects(); updateLegendState(); navigate("projects"); }));
    updateLegendState();
  }
  function updateLegendState() { $$("[data-category-filter]").forEach(button => button.classList.toggle("active", state.category === button.dataset.categoryFilter)); }

  function renderNarrative() {
    const target = $("#narrative-grid");
    const cards = state.data.narrative || [];
    if (!target) return;
    target.innerHTML = cards.map(item => `<article class="narrative-card"><p class="eyebrow">${escapeHTML(item.kicker)}</p><h3>${escapeHTML(item.title)}</h3><p>${escapeHTML(item.body)}</p></article>`).join("");
  }

  function makeBars(target, large = false) {
    if (!target) return;
    const timeline = state.data.timeline || [];
    const max = Math.max(1, ...timeline.map(day => Number(day.count || 0)));
    target.innerHTML = timeline.map(day => {
      const count = Number(day.count || 0);
      const meaningful = Number(day.meaningfulCount || 0);
      const height = count ? Math.max(7, count / max * 100) : 3;
      return `<span class="activity-bar ${meaningful ? "meaningful" : ""}" style="height:${height}%" title="${escapeHTML(day.date)} · ${count} 次动作"></span>`;
    }).join("");
    const first = timeline[0]; const last = timeline[timeline.length - 1];
    if (!large) { $("#activity-start").textContent = first?.label || "—"; }
    else { $("#timeline-start").textContent = first?.label || "—"; $("#timeline-end").textContent = last?.label || "—"; }
  }

  function renderTimeline() {
    makeBars($("#activity-bars")); makeBars($("#big-activity-bars"), true);
    const highlights = state.data.highlights || state.data.commits || [];
    const list = $("#commit-list");
    if (!list) return;
    $("#highlight-count").textContent = `${Math.min(highlights.length, 48)} HIGHLIGHTS`;
    list.innerHTML = highlights.slice(0, 48).map(commit => {
      const repoName = commit.repo?.split("/").pop() || "unknown";
      const message = escapeHTML(commit.message || "未命名提交");
      const type = (commit.message || "").split(":")[0].toUpperCase();
      return `<a class="commit-item" href="${escapeHTML(commit.url || "#")}" target="_blank" rel="noreferrer"><time class="commit-date">${dateLabel(commit.date)}</time><div class="commit-message"><p><span class="commit-type">${escapeHTML(type || "MOVE")}</span>${message}</p><span>${escapeHTML(repoName)} / ${escapeHTML(commit.branch || "main")}</span></div></a>`;
    }).join("") || `<div class="no-results">还没有近期提交记录。</div>`;
  }

  function repoMatches(repo) {
    const haystack = [repo.name, repo.fullName, repo.description, repo.defaultBranch, ...(repo.categories || []), ...(repo.branches || []).map(branch => branch.name)].join(" ").toLowerCase();
    return (state.category === "all" || (repo.categories || []).includes(state.category)) && (!state.query || haystack.includes(state.query.toLowerCase()));
  }
  function renderFilters() {
    const target = $("#project-filters"); if (!target) return;
    const buttons = [{ id: "all", name: "全部", color: COLORS.blue }, ...(state.data.categories || [])];
    target.innerHTML = buttons.map(item => `<button class="filter-button ${state.category === item.id ? "active" : ""}" style="--filter-color:${item.color || COLORS[item.id] || COLORS.blue}" data-project-filter="${escapeHTML(item.id)}">${escapeHTML(item.name)}</button>`).join("");
    $$("[data-project-filter]", target).forEach(button => button.addEventListener("click", () => { state.category = button.dataset.projectFilter; renderProjects(); updateLegendState(); }));
  }
  function renderProjects() {
    renderFilters();
    const repos = (state.data.repositories || []).filter(repoMatches);
    $("#project-result-count").textContent = `${repos.length} / ${state.data.repositories?.length || 0} WORLDS`;
    const target = $("#project-grid");
    if (!repos.length) { target.innerHTML = `<div class="no-results">没有找到这颗星。<br><span style="font-size:11px">试试另一个关键词，或者把筛选放回全部。</span></div>`; return; }
    target.innerHTML = repos.map(repo => {
      const color = colorFor(repo); const category = categoryName(categoryFor(repo));
      return `<article class="project-card" data-project-id="${escapeHTML(repo.id)}" style="--project-color:${color}"><div class="project-top"><span class="project-category">${escapeHTML(category.toUpperCase())}</span><span class="project-activity">${formatNumber(repo.meaningfulCommitCount ?? repo.recentCommitCount)} MOVES</span></div><h3>${escapeHTML(repo.name)}</h3><span class="project-fullname">${escapeHTML(repo.fullName)}</span><p class="project-desc">${escapeHTML(repo.description)}</p><div class="project-footer"><span class="project-branches">${formatNumber(repo.branchCount)} 个 branch · ${repo.latestCommit ? shortDate(repo.latestCommit.date, true) : "无近期记录"}</span><span class="project-arrow">↗</span></div></article>`;
    }).join("");
    $$("[data-project-id]", target).forEach(card => card.addEventListener("click", () => openProject(card.dataset.projectId)));
  }

  function openProject(id) {
    const repo = (state.data.repositories || []).find(item => item.id === id); if (!repo) return;
    const color = colorFor(repo); const category = categoryName(categoryFor(repo));
    const branches = (repo.branches || []).map(branch => { const latest = branch.latestCommit ? `<small>${escapeHTML(branch.latestCommit.message || "未命名提交")}</small>` : "<small>这个分支最近没有可见动作</small>"; return `<div class="modal-branch"><div><span>⌁ ${escapeHTML(branch.name)}</span>${latest}</div><span>${formatNumber(branch.recentCommitCount)} recent commits</span></div>`; }).join("") || `<div class="modal-branch"><span>暂无 branch 数据</span></div>`;
    const latest = repo.latestCommit ? `<div class="modal-latest"><p>${escapeHTML(repo.latestCommit.message || "未命名提交")}</p><span>${escapeHTML(shortDate(repo.latestCommit.date, true))} · ${escapeHTML(repo.latestCommit.sha || "")}</span></div>` : `<div class="modal-latest"><p>这个世界最近没有留下可见的 commit。</p></div>`;
    const recent = (repo.branches || []).flatMap(branch => (branch.recentCommits || []).map(commit => ({ ...commit, branch: branch.name }))).sort((a, b) => (b.date || "").localeCompare(a.date || "")).slice(0, 5);
    const recentHtml = recent.length ? recent.map(commit => `<div class="modal-recent"><span>${escapeHTML(dateLabel(commit.date))}</span><p>${escapeHTML(commit.message || "未命名提交")}</p><small>${escapeHTML(commit.branch || "main")}</small></div>`).join("") : `<div class="modal-recent"><p>该快照没有展开近期提交列表。</p></div>`;
    $("#modal-content").innerHTML = `<p class="modal-kicker" style="color:${color}">${escapeHTML(category.toUpperCase())} / PROJECT ARCHIVE</p><h2 class="modal-title" id="modal-title">${escapeHTML(repo.name)}</h2><p class="modal-fullname">${escapeHTML(repo.fullName)} · ${repo.private ? "PRIVATE" : "PUBLIC"}</p><p class="modal-description">${escapeHTML(repo.description)}</p><div class="modal-grid"><div class="modal-stat"><span>RECENT MOVES</span><b>${formatNumber(repo.meaningfulCommitCount ?? repo.recentCommitCount)}</b></div><div class="modal-stat"><span>BRANCHES</span><b>${formatNumber(repo.branchCount)}</b></div><div class="modal-stat"><span>DEFAULT</span><b>${escapeHTML(repo.defaultBranch || "—")}</b></div></div><p class="modal-section-title">LATEST SIGNAL</p>${latest}<p class="modal-section-title">PARALLEL UNIVERSES</p>${branches}<p class="modal-section-title">RECENT MOVES</p><div class="modal-recent-list">${recentHtml}</div><div style="margin-top:26px"><a class="button button-outline" href="${escapeHTML(repo.latestCommit?.url || "#")}" target="_blank" rel="noreferrer">在 GitHub 打开 <span>↗</span></a></div>`;
    const dialog = $("#project-modal"); $("#modal-backdrop").hidden = false; if (typeof dialog.showModal === "function") dialog.showModal(); else dialog.setAttribute("open", "");
  }
  function closeModal() { const dialog = $("#project-modal"); $("#modal-backdrop").hidden = true; if (dialog.open && typeof dialog.close === "function") dialog.close(); else dialog.removeAttribute("open"); }

  function drawConstellation() {
    const canvas = $("#constellation-canvas"); const stage = $("#constellation-stage"); if (!canvas || !stage) return;
    const rect = stage.getBoundingClientRect(); const ratio = Math.min(window.devicePixelRatio || 1, 2); canvas.width = rect.width * ratio; canvas.height = rect.height * ratio; canvas.style.width = `${rect.width}px`; canvas.style.height = `${rect.height}px`;
    const context = canvas.getContext("2d"); context.setTransform(ratio, 0, 0, ratio, 0, 0); context.clearRect(0, 0, rect.width, rect.height);
    const center = { x: rect.width * .5, y: rect.height * .5 }; const groups = { learning: -2.35, engineering: -.8, agent: .45, personal: 2.25 };
    const repos = state.data.repositories || []; state.nodes = repos.map((repo, index) => {
      const category = categoryFor(repo); const base = groups[category] ?? 0; const spread = ((index * 1.618) % 1) - .5; const radius = Math.min(rect.width, rect.height) * (.2 + ((index * 37) % 100) / 100 * .26); const angle = base + spread * 1.45; return { repo, x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius * .72, r: Math.max(4, Math.min(9, 4 + Math.log1p(repo.activityScore || 1))), color: colorFor(repo) };
    });
    // faint orbit lanes
    [0.22, .35, .49].forEach((ratio, index) => { context.beginPath(); context.ellipse(center.x, center.y, rect.width * ratio, rect.height * ratio * .64, -.18, 0, Math.PI * 2); context.strokeStyle = index === 1 ? "rgba(115,217,255,.12)" : "rgba(214,224,255,.055)"; context.lineWidth = 1; context.stroke(); });
    state.nodes.forEach(node => { context.beginPath(); context.moveTo(center.x, center.y); context.lineTo(node.x, node.y); context.strokeStyle = `${node.color}22`; context.lineWidth = 1; context.stroke(); });
    // center pulse
    context.beginPath(); context.arc(center.x, center.y, 26, 0, Math.PI * 2); context.fillStyle = "rgba(115,217,255,.05)"; context.fill(); context.strokeStyle = "rgba(115,217,255,.35)"; context.stroke();
    state.nodes.forEach(node => { const gradient = context.createRadialGradient(node.x, node.y, 0, node.x, node.y, node.r * 4); gradient.addColorStop(0, `${node.color}aa`); gradient.addColorStop(1, `${node.color}00`); context.beginPath(); context.fillStyle = gradient; context.arc(node.x, node.y, node.r * 4, 0, Math.PI * 2); context.fill(); context.beginPath(); context.fillStyle = node.color; context.arc(node.x, node.y, node.r, 0, Math.PI * 2); context.fill(); context.beginPath(); context.strokeStyle = `${node.color}66`; context.arc(node.x, node.y, node.r + 4, 0, Math.PI * 2); context.stroke(); context.fillStyle = "rgba(237,240,251,.78)"; context.font = "10px " + getComputedStyle(document.body).fontFamily; context.fillText(node.repo.name, node.x + node.r + 8, node.y + 3); });
    const tooltip = $("#star-tooltip");
    const findNode = event => { const bounds = canvas.getBoundingClientRect(); const x = event.clientX - bounds.left; const y = event.clientY - bounds.top; return { x, y, node: state.nodes.find(item => Math.hypot(item.x - x, item.y - y) < item.r + 12) }; };
    canvas.onmousemove = event => { const hit = findNode(event); if (!hit.node) { tooltip.hidden = true; canvas.style.cursor = "crosshair"; return; } const repo = hit.node.repo; tooltip.innerHTML = `<b>${escapeHTML(repo.name)}</b><span>${escapeHTML(categoryName(categoryFor(repo)))} · ${formatNumber(repo.meaningfulCommitCount ?? repo.recentCommitCount)} moves</span><small>点击打开档案</small>`; tooltip.style.left = `${Math.min(hit.x + 15, rect.width - 190)}px`; tooltip.style.top = `${Math.max(12, hit.y - 12)}px`; tooltip.hidden = false; canvas.style.cursor = "pointer"; };
    canvas.onmouseleave = () => { tooltip.hidden = true; canvas.style.cursor = "crosshair"; };
    canvas.onclick = event => { const hit = findNode(event); if (hit.node) openProject(hit.node.repo.id); };
  }

  function renderSparks() {
    const first = $("#spark-first"); const second = $("#spark-second"); if (!first || !second) return;
    const options = (state.data.repositories || []).map(repo => `<option value="${escapeHTML(repo.id)}">${escapeHTML(repo.name)}</option>`).join(""); first.innerHTML = options; second.innerHTML = options; if (second.options.length > 1) second.selectedIndex = 1;
    $("#spark-button").onclick = generateSpark;
    const unfinished = $("#unfinished-grid"); const repos = (state.data.repositories || []).filter(repo => (repo.branches || []).length > 1 || !repo.latestCommit);
    unfinished.innerHTML = (repos.length ? repos.slice(0, 6) : (state.data.repositories || []).slice(-3)).map(repo => `<article class="unfinished-card"><p>${escapeHTML(repo.name)}</p><span>${formatNumber(repo.branchCount)} 个可能性 · ${repo.latestCommit ? "仍有信号" : "等待回访"}</span></article>`).join("") || `<article class="unfinished-card"><p>等你把第一颗星放进来。</p><span>LOCAL / UNFINISHED</span></article>`;
  }
  const sparkTemplates = [
    (a, b) => ({ title: `把「${a.name}」做成可以被另一个人使用的工具`, body: `从 ${a.name} 里拿出一个最有力量的机制，再用 ${b.name} 的表达方式把它交给真实的人。不要先做完整平台，先做一个 10 分钟能走完的体验。`, steps: ["找出一个核心动作", "写一个最小场景", "让一个人实际走完"] }),
    (a, b) => ({ title: `给「${a.name}」接上一条来自「${b.name}」的记忆`, body: `你已经分别拥有这两个世界。下一步不是再开一个仓库，而是在它们之间留一扇门：让一次学习、一次工程计算或一次情绪被记录下来，并在合适的时候回来。`, steps: ["定义一条记忆", "设计回访入口", "观察它是否真的有用"] }),
    (a, b) => ({ title: `做一个只解决一个瞬间的 ${b.name} × ${a.name} 实验`, body: `把 ${a.name} 的复杂度压缩到一个瞬间，再让 ${b.name} 提供语气、节奏或问题意识。这个实验的成功标准不是参数，而是一个人用完之后愿意再来一次。`, steps: ["砍掉 80% 功能", "保留一个惊喜", "记录使用者的第一句话"] }),
  ];
  function generateSpark() {
    const a = (state.data.repositories || []).find(repo => repo.id === $("#spark-first").value); const b = (state.data.repositories || []).find(repo => repo.id === $("#spark-second").value); if (!a || !b || a.id === b.id) { showToast("请选择两颗不同的星。", "pink"); return; }
    const seed = Math.floor(a.name.length + b.name.length + (a.activityScore || 0)) % sparkTemplates.length; const result = sparkTemplates[seed](a, b); state.spark = result;
    const signal = `${a.name}：${formatNumber(a.branchCount)} branch / ${formatNumber(a.meaningfulCommitCount ?? a.recentCommitCount)} moves；${b.name}：${formatNumber(b.branchCount)} branch / ${formatNumber(b.meaningfulCommitCount ?? b.recentCommitCount)} moves`;
    $("#spark-result").innerHTML = `<div class="spark-result-filled"><p class="eyebrow">SIGNAL ACQUIRED / ${escapeHTML(a.name.toUpperCase())} × ${escapeHTML(b.name.toUpperCase())}</p><h2>${escapeHTML(result.title)}</h2><p>${escapeHTML(result.body)}</p><div class="spark-steps">${result.steps.map((step, index) => `<div class="spark-step"><b>0${index + 1}</b><span>${escapeHTML(step)}</span></div>`).join("")}</div><p class="spark-signal"><span>DATA BASIS</span>${escapeHTML(signal)}</p><button class="button button-outline spark-copy" id="spark-copy">复制实验 brief <span>↗</span></button></div>`;
    $("#spark-copy").onclick = async () => { const brief = `${result.title}

${result.body}

步骤：${result.steps.join("；")}

数据依据：${signal}`; try { await navigator.clipboard.writeText(brief); showToast("实验 brief 已复制。", "blue"); } catch (_) { showToast("复制失败，但 brief 已经生成在右侧。", "pink"); } };
    showToast("一条新的轨道被点亮了。", "blue");
  }

  function renderLetter() {
    const stats = state.data.stats || {}; const categories = (state.data.categories || []).filter(item => item.repoCount).map(item => item.name).join("、") || "几个还在形成中的方向";
    const body = $("#letter-body"); if (!body) return;
    body.innerHTML = `<p>如果你在未来打开这封信，说明今天的你又走了一段。</p><p>现在的你有 <strong>${formatNumber(stats.repositories)} 个仓库</strong>、<strong>${formatNumber(stats.branches)} 条 branch</strong>，最近一个月留下了 <strong>${formatNumber(stats.meaningfulCommits ?? stats.recentCommits)} 次非 merge 的动作</strong>。这些数字不证明你是谁，但它们证明：你没有只停留在想。</p><p>你把学习系统、工程现场、AI 工作流和重要的人放在同一个账号里。看起来跨度很大，其实它们都在问同一个问题：<strong>怎样把一个复杂的念头，变成别人能够真正抵达的东西？</strong></p><p>希望你不要因为轨道分叉，就误以为自己走散了。${escapeHTML(categories)} 不是互相竞争的身份，它们是同一个人在不同光线下留下的轮廓。</p><p>继续做那些看起来暂时没有必要、但完成之后会让你心里亮一下的东西。也记得给已经完成的项目留一点回声。</p>`;
    $("#fact-list").innerHTML = [`${formatNumber(stats.repositories)} 个仓库，${formatNumber(stats.branches)} 条 branch`, `最近一个月 ${formatNumber(stats.recentCommits)} 条提交记录`, `当前识别出 ${formatNumber(stats.activeRepositories)} 个活跃项目`].map(item => `<li>${escapeHTML(item)}</li>`).join("");
    $("#interpretation-list").innerHTML = ["你在反复发明新的入口", "你擅长把混乱变成下一步", "技术是手段，抵达才是方向"].map(item => `<li>${escapeHTML(item)}</li>`).join("");
    const date = new Date(); const formatted = Number.isNaN(date.getTime()) ? "2026.09.01" : `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, "0")}.${String(date.getDate()).padStart(2, "0")}`; $("#letter-date").textContent = `${formatted} · LOCAL ARCHIVE`; $("#constellation-date").textContent = formatted;
    $("#download-letter").onclick = () => { const text = [...body.querySelectorAll("p")].map(p => p.textContent).join("\n\n"); const blob = new Blob([`写给未来的你\n\n${text}\n\n— 乙鸣星图 / ${formatted}`], { type: "text/plain;charset=utf-8" }); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `yiming-letter-${formatted.replaceAll(".", "-")}.txt`; link.click(); URL.revokeObjectURL(link.href); showToast("这封信已经保存到你的电脑。", "gold"); };
  }

  function navigate(view) {
    state.activeView = view; $$(".view").forEach(section => section.classList.toggle("active", section.dataset.view === view)); $$("[data-view-target]").forEach(item => { if (item.classList.contains("nav-item")) item.classList.toggle("active", item.dataset.viewTarget === view); }); const names = { overview: "OVERVIEW", projects: "PROJECTS", timeline: "TIMELINE", sparks: "SPARKS", capsule: "CAPSULE" }; $("#breadcrumb-current").textContent = names[view] || "OVERVIEW"; $("#sidebar").classList.remove("open"); window.scrollTo({ top: 0, behavior: "smooth" }); if (view === "overview") setTimeout(drawConstellation, 30); }

  let toastTimer;
  function showToast(message) { const toast = $("#toast"); toast.textContent = message; toast.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove("show"), 2600); }

  function bindEvents() {
    $$('[data-view-target]').forEach(item => item.addEventListener("click", () => navigate(item.dataset.viewTarget)));
    $("#project-search").addEventListener("input", event => { state.query = event.target.value.trim(); renderProjects(); });
    $("#mobile-menu").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
    $("#modal-close").addEventListener("click", closeModal); $("#modal-backdrop").addEventListener("click", closeModal); $("#project-modal").addEventListener("cancel", closeModal); window.addEventListener("resize", () => { if (state.activeView === "overview") drawConstellation(); });
  }

  async function init() {
    state.data = await loadData();
    const generated = state.data.stats?.repositories > 0 && !(state.data.privacy?.sourceTypes || []).includes("demo"); $("#data-status-text").textContent = generated ? "LOCAL SNAPSHOT" : "DEMO SNAPSHOT"; $("#topbar-date").textContent = shortDate(state.data.generatedAt, true).replaceAll(".", ".");
    renderStats(); renderLegend(); renderNarrative(); renderTimeline(); renderProjects(); renderSparks(); renderLetter(); bindEvents(); setTimeout(drawConstellation, 80);
  }
  init();
})();
