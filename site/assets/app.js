/* 美剧生词本 — offline-first flashcard app. */
(function () {
  "use strict";

  var DB = window.VOCAB_DB || { episodes: [], words: [], generated: null };
  var KEY = "mtv1";
  var S = load();

  function load() {
    try {
      var raw = localStorage.getItem(KEY);
      if (raw) return JSON.parse(raw);
    } catch (e) { /* private mode or corrupt value */ }
    return { status: {}, theme: null, idx: 0, ep: null };
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* quota or private mode */ }
  }

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }

  /* ---------- index helpers ---------- */
  var byEpisode = {}, wordKey = {}, lemmaKey = {};
  DB.episodes.forEach(function (ep) { byEpisode[ep.key] = ep; });
  DB.words.forEach(function (w) {
    wordKey[w.key] = w;
    if (w.lemma) lemmaKey[w.episodeKey + "|" + w.lemma] = w.key;
  });

  function statusOf(key) { return S.status[key] || "new"; }
  function setStatus(key, st) {
    if (st === "new") delete S.status[key]; else S.status[key] = st;
    save();
  }

  // A word may repeat across episodes; the card deck keys on "episode|word".
  function keyFor(w) { return w.key; }

  /* ---------- theme ---------- */
  function applyTheme() {
    var t = S.theme;
    if (!t) t = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", t);
    var m = $('meta[name="theme-color"]');
    if (m) m.setAttribute("content", t === "light" ? "#f7f8fa" : "#0f1115");
  }
  $("#btn-theme").addEventListener("click", function () {
    var cur = document.documentElement.getAttribute("data-theme");
    S.theme = cur === "light" ? "dark" : "light";
    save(); applyTheme();
  });

  /* ---------- filters ---------- */
  function fillEpisodeSelects() {
    var opts = DB.episodes.map(function (ep) {
      return '<option value="' + esc(ep.key) + '">' + esc(ep.title) + "</option>";
    }).join("");
    $("#filter-episode").innerHTML = '<option value="">全部剧集</option>' + opts;
    $("#script-episode").innerHTML = opts;
  }

  // One selection drives every view; stored so the app reopens on the same episode.
  function currentEpisode() {
    var v = S.ep || "";
    if (v && byEpisode[v]) return v;
    return DB.episodes.length ? DB.episodes[0].key : "";
  }

  function selectEpisode(key) {
    if (!byEpisode[key]) return;
    S.ep = key; S.idx = 0; pos = 0;
    save();
    $("#filter-episode").value = key;
    $("#script-episode").value = key;
    reloadDeck(); renderList(); renderScript(); renderStats(); markActiveEpCards();
  }

  /* ---------- library / episode picker ---------- */
  function renderLibrary() {
    var body = $("#library-body");
    body.innerHTML = "";
    if (!DB.episodes.length) {
      body.appendChild(el("div", "empty", "还没有剧集。<br>先用 skill 提取一集，这里就会出现选集界面。"));
      return;
    }

    // Group episodes by show, preserving first-seen order.
    var groups = {}, order = [];
    DB.episodes.forEach(function (ep) {
      var g = ep.show || "其他";
      if (!groups[g]) { groups[g] = []; order.push(g); }
      groups[g].push(ep);
    });

    order.forEach(function (g) {
      var eps = groups[g];
      var meta = null;
      for (var i = 0; i < eps.length; i++) {
        var cand = eps[i].showSlug && DB.shows[eps[i].showSlug];
        if (cand) { meta = cand; break; }
      }

      var sec = el("div", "show-sec");
      var head = el("div", "show-head");
      if (meta && meta.cover) {
        var th = el("img", "show-thumb");
        th.alt = meta.title || g;
        th.decoding = "async";
        // Insert first, then assign src: assigning before insertion can leave
        // the image pending forever in some engines.
        head.appendChild(th);
        th.src = meta.cover;
      }
      var wc = 0;
      eps.forEach(function (e) {
        wc += DB.words.filter(function (w) { return w.episodeKey === e.key; }).length;
      });
      var sub = [meta && meta.year, meta && (meta.genres || []).slice(0, 3).join(" · ")]
        .filter(Boolean).join(" · ");
      head.appendChild(el("div", "show-meta",
        '<h2 class="show-title">' + esc((meta && meta.title) || g) + "</h2>" +
        (sub ? '<div class="show-sub">' + esc(sub) + "</div>" : "")));
      head.appendChild(el("div", "show-count", eps.length + " 集<br>" + wc + " 词"));
      sec.appendChild(head);

      var grid = el("div", "ep-grid");
      eps.forEach(function (ep) { grid.appendChild(epCard(ep, meta)); });
      sec.appendChild(grid);
      body.appendChild(sec);
    });

    markActiveEpCards();
  }

  function epCard(ep, meta) {
    var ws = DB.words.filter(function (w) { return w.episodeKey === ep.key; });
    var done = ws.filter(function (w) { return statusOf(keyFor(w)) === "mastered"; }).length;
    var pct = ws.length ? Math.round((done / ws.length) * 100) : 0;

    var btn = el("button", "ep-card");
    btn.setAttribute("data-ep", ep.key);

    var art = el("div", "ep-art");
    if (meta && meta.cover) {
      var img = el("img");
      img.alt = "";
      img.decoding = "async";
      art.appendChild(img);
      img.src = meta.cover;
    }
    art.appendChild(el("div", "ep-scrim"));
    art.appendChild(el("div", "ep-code", ep.code.toUpperCase()));
    var foot = el("div", "ep-foot", ws.length && done === ws.length ? "✓" : String(done));
    if (ws.length && done === ws.length) foot.className = "ep-foot done";
    art.appendChild(foot);
    art.appendChild(el("div", "ep-title", ep.epTitle || ep.title || ep.code));

    btn.appendChild(art);
    btn.appendChild(el("div", "ep-bar", "<i style='width:" + pct + "%'></i>"));

    btn.addEventListener("click", function () {
      selectEpisode(ep.key);
      showTab("cards");
    });
    return btn;
  }

  function markActiveEpCards() {
    var cur = currentEpisode();
    $$(".ep-card").forEach(function (c) {
      c.classList.toggle("is-active", c.getAttribute("data-ep") === cur);
    });
  }

  function showTab(name) {
    $$(".tab").forEach(function (x) { x.classList.toggle("is-active", x.dataset.tab === name); });
    $$(".view").forEach(function (v) { v.classList.remove("is-active"); });
    $("#view-" + name).classList.add("is-active");
    $("#app").dataset.view = name;
    if (name === "library") renderLibrary();
    if (name === "list") renderList();
    if (name === "script") renderScript();
    if (name === "stats") renderStats();
  }

  function deck() {
    var ep = $("#filter-episode").value;
    var lv = $("#filter-level").value;
    var st = $("#filter-status").value;
    return DB.words.filter(function (w) {
      if (ep && w.episodeKey !== ep) return false;
      if (lv && w.level !== lv) return false;
      if (st && statusOf(keyFor(w)) !== st) return false;
      return true;
    });
  }

  /* ---------- cards ---------- */
  var deckCache = [], pos = 0, flipped = false;

  function renderCard() {
    var stage = $("#card-stage");
    stage.innerHTML = "";

    if (!deckCache.length) {
      stage.appendChild(el("div", "empty", "当前筛选条件下没有词条。<br>试试放宽剧集、级别或状态筛选。"));
      $("#progress-fill").style.width = "0%";
      $("#progress-count").textContent = "0 / 0";
      $("#progress-pct").textContent = "0%";
      ["#btn-prev", "#btn-next", "#btn-flip", "#btn-known", "#btn-unsure"].forEach(function (s) {
        $(s).disabled = true;
      });
      return;
    }
    if (pos >= deckCache.length) pos = deckCache.length - 1;
    if (pos < 0) pos = 0;

    var w = deckCache[pos];
    var st = statusOf(keyFor(w));
    flipped = false;

    var card = el("div", "flashcard");

    var front = el("div", "fc-face fc-front");
    front.appendChild(el("div", "fc-head",
      '<h2 class="fc-word">' + esc(w.word) + "</h2>" +
      '<span class="badge badge-' + esc(w.level) + '">' + esc(w.level) + "</span>"));
    front.appendChild(el("div", "fc-pos", esc(w.pos || "")));
    front.appendChild(el("div", "fc-phon", esc(w.phonetic || "")));
    if (w.meaning_en) front.appendChild(el("div", "fc-row", '<div class="fc-def-en">' + esc(w.meaning_en) + "</div>"));
    front.appendChild(el("div", "fc-hint", "点击卡片或按「看释义」翻转"));

    var back = el("div", "fc-face fc-back");
    back.appendChild(el("div", "fc-head",
      '<h2 class="fc-word">' + esc(w.word) + "</h2>" +
      '<span class="badge badge-' + esc(w.level) + '">' + esc(w.level) + "</span>"));
    if (w.meaning_cn) {
      back.appendChild(el("div", "fc-row",
        '<div class="fc-label">中文释义</div><div class="fc-def-cn">' + esc(w.meaning_cn) + "</div>"));
    }
    if (w.quote) {
      back.appendChild(el("div", "fc-row",
        '<div class="fc-label">剧中台词</div><div class="fc-quote">' + esc(w.quote) + "</div>" +
        (w.quote_cn ? '<div class="fc-quote-cn">' + esc(w.quote_cn) + "</div>" : "")));
    }
    if (w.example) {
      back.appendChild(el("div", "fc-row",
        '<div class="fc-label">例句</div><div class="fc-example">' + esc(w.example) + "</div>" +
        (w.example_cn ? '<div class="fc-example-cn">' + esc(w.example_cn) + "</div>" : "")));
    }
    if (w.scene) {
      back.appendChild(el("div", "fc-row",
        '<div class="fc-label">场景</div><div class="fc-example-cn">' + esc(w.scene) + "</div>"));
    }
    if (w.note) {
      back.appendChild(el("div", "fc-row",
        '<div class="fc-label">用法提示</div><div class="fc-note">' + esc(w.note) + "</div>"));
    }

    card.appendChild(front);
    card.appendChild(back);
    card.addEventListener("click", function () { flip(); });
    stage.appendChild(card);

    $("#progress-count").textContent = (pos + 1) + " / " + deckCache.length;
    $("#progress-pct").textContent =
      Math.round(((pos + 1) / deckCache.length) * 100) + "%";
    $("#progress-fill").style.width = ((pos + 1) / deckCache.length) * 100 + "%";
    var cur = statusOf(keyFor(w));
    $("#btn-known").textContent = cur === "mastered" ? "已掌握 ✓" : "认识";
    $("#btn-known").style.color = cur === "mastered" ? "var(--b2)" : "";
    $("#btn-unsure").textContent = cur === "learning" ? "复习中 ✓" : "模糊";
    $("#btn-unsure").style.color = cur === "learning" ? "var(--warn)" : "";
  }

  function flip() {
    var card = $(".flashcard");
    if (!card) return;
    flipped = !flipped;
    card.classList.toggle("is-flipped", flipped);
    $("#btn-flip").textContent = flipped ? "翻回去" : "看释义";
  }

  function mark(st) {
    var w = deckCache[pos];
    if (!w) return;
    setStatus(keyFor(w), st);
    goto(1);
  }
  function goto(d) {
    pos = Math.max(0, Math.min(deckCache.length - 1, pos + d));
    S.idx = pos; save();
    renderCard();
  }

  $("#btn-flip").addEventListener("click", flip);
  $("#btn-known").addEventListener("click", function () { mark("mastered"); });
  $("#btn-unsure").addEventListener("click", function () { mark("learning"); });
  $("#btn-next").addEventListener("click", function () { goto(1); });
  $("#btn-prev").addEventListener("click", function () { goto(-1); });

  function reloadDeck() {
    deckCache = deck();
    if (pos >= deckCache.length) pos = deckCache.length - 1;
    if (pos < 0) pos = 0;
    renderCard();
  }
  $("#filter-episode").addEventListener("change", function () {
    // Picking from the dropdown is also a selection; keep the library in sync.
    var v = this.value;
    if (v) {
      S.ep = v; S.idx = 0; pos = 0; save();
      $("#script-episode").value = v;
      markActiveEpCards();
    }
    reloadDeck();
  });
  $("#filter-level").addEventListener("change", function () { pos = 0; reloadDeck(); });
  $("#filter-status").addEventListener("change", function () { pos = 0; reloadDeck(); });

  /* ---------- list ---------- */
  $("#search").addEventListener("input", renderList);

  function renderList() {
    var q = $("#search").value.trim().toLowerCase();
    var ul = $("#word-list");
    ul.innerHTML = "";
    var rows = DB.words.filter(function (w) {
      if (!q) return true;
      return (w.word + " " + (w.meaning_cn || "") + " " + (w.meaning_en || "") + " " + (w.meaning_cn || ""))
        .toLowerCase().indexOf(q) >= 0;
    });
    if (!rows.length) {
      ul.appendChild(el("li", "empty", "没有匹配的词条。"));
      return;
    }
    rows.forEach(function (w) {
      var key = keyFor(w);
      var st = statusOf(key);
      var li = el("li", "word-item");
      var head = el("button", "wi-head",
        '<span class="wi-dot ' + st + '"></span>' +
        '<span class="wi-word">' + esc(w.word) + "</span>" +
        '<span class="badge badge-' + esc(w.level) + '">' + esc(w.level) + "</span>" +
        '<span class="wi-chev">›</span>');
      head.addEventListener("click", function () {
        var open = li.classList.toggle("is-open");
        head.setAttribute("aria-expanded", String(open));
      });
      li.appendChild(head);
      li.appendChild(el("div", "wi-body", bodyHtml(w)));
      ul.appendChild(li);
    });
  }

  function bodyHtml(w) {
    var h = "";
    if (w.phonetic) h += '<div class="fc-phon">' + esc(w.phonetic) + "</div>";
    if (w.meaning_en) h += '<div class="fc-def-en">' + esc(w.meaning_en) + "</div>";
    if (w.meaning_cn) h += '<div class="fc-def-cn">' + esc(w.meaning_cn) + "</div>";
    if (w.pos) h += '<div class="fc-pos" style="margin-top:4px">' + esc(w.pos) + "</div>";
    if (w.quote) {
      h += '<div class="fc-row"><div class="fc-label">剧中台词 · ' + esc(w.episodeTitle || "") + "</div>" +
        '<div class="fc-quote">' + esc(w.quote) + "</div>" +
        (w.quote_cn ? '<div class="fc-quote-cn">' + esc(w.quote_cn) + "</div>" : "") + "</div>";
    }
    if (w.example) {
      h += '<div class="fc-row"><div class="fc-label">例句</div><div class="fc-example">' + esc(w.example) + "</div>" +
        (w.example_cn ? '<div class="fc-example-cn">' + esc(w.example_cn) + "</div>" : "") + "</div>";
    }
    if (w.note) {
      h += '<div class="fc-row"><div class="fc-note">' + esc(w.note) + "</div></div>";
    }
    return h;
  }

  /* ---------- script ---------- */
  function renderScript() {
    var key = $("#script-episode").value;
    var ep = byEpisode[key];
    var body = $("#script-body");
    body.innerHTML = "";
    if (!ep) { body.appendChild(el("div", "empty", "暂无剧集原文。")); return; }

    $("#script-meta").innerHTML =
      esc(ep.title) + (ep.sourceUrl ? " · <a href=\"" + esc(ep.sourceUrl) +
      '" target="_blank" rel="noopener">来源</a>"' : "");

    var tap = $("#script-tap").checked;
    body.classList.toggle("tapmode", tap);

    var hitSet = {};
    DB.words.forEach(function (w) {
      if (w.episodeKey === key) hitSet[w.lemma.toLowerCase()] = 1;
    });

    ep.lines.forEach(function (ln) {
      var line = el("div", "ln");
      var marked = false;
      // Wrap known words so tapping them can show the card.
      ln.split(/(\s+)/).forEach(function (part) {
        if (!part || /^\s+$/.test(part)) { line.appendChild(document.createTextNode(part)); return; }
        var bare = part.replace(/^[^A-Za-z'-]+|[^A-Za-z'-]+$/g, "");
        var low = bare.toLowerCase();
        var inDeck = tap && hitSet[low];
        var node = el("span", "tok", esc(part));
        if (inDeck) {
          node.setAttribute("data-w", "1");
          node.setAttribute("data-key", lemmaKey[key + "|" + low] || "");
          if (!marked) { line.setAttribute("data-hit", "1"); marked = true; }
        }
        line.appendChild(node);
      });
      body.appendChild(line);
    });

    if (tap) {
      $$(".tok[data-w='1']", body).forEach(function (t) {
        t.addEventListener("click", function (ev) {
          ev.stopPropagation();
          openSheet(t.getAttribute("data-key"));
        });
      });
    }
  }
  $("#script-episode").addEventListener("change", function () {
    var v = this.value;
    if (v) {
      S.ep = v; save();
      $("#filter-episode").value = v;
      markActiveEpCards();
    }
    renderScript();
  });
  $("#script-tap").addEventListener("change", renderScript);

  /* ---------- sheet ---------- */
  function openSheet(key) {
    var w = wordKey[key];
    if (!w) return;
    var b = $("#sheet-body");
    b.innerHTML =
      '<h3 class="sheet-title">' + esc(w.word) + "</h3>" +
      '<div class="sheet-phon">' + esc(w.phonetic || "") + " · " + esc(w.pos || "") +
      ' · <span class="badge badge-' + esc(w.level) + '">' + esc(w.level) + "</span></div>" +
      bodyHtml(w);
    $("#sheet").hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeSheet() {
    $("#sheet").hidden = true;
    document.body.style.overflow = "";
  }
  $$("[data-close]").forEach(function (n) { n.addEventListener("click", closeSheet); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeSheet();
  });

  /* ---------- stats ---------- */
  function renderStats() {
    var counts = { new: 0, learning: 0, mastered: 0 };
    DB.words.forEach(function (w) { counts[statusOf(keyFor(w))]++; });
    var total = DB.words.length || 1;
    var pct = function (n) { return Math.round((n / total) * 100) + "%"; };
    var names = { new: "未学习", learning: "复习中", mastered: "已掌握" };
    var colors = { new: "var(--fg-faint)", learning: "var(--warn)", mastered: "var(--b2)" };

    var h = '<div class="stat-card"><div class="stat-num">' +
      Math.round((counts.mastered / total) * 100) + '%</div>' +
      '<div class="stat-cap">总体掌握度 · 共 ' + DB.words.length + " 个词条，" +
      DB.episodes.length + " 集</div></div>";

    h += '<div class="stat-card"><div class="stat-grid">' +
      ["new", "learning", "mastered"].map(function (k) {
        return '<div><div class="stat-num" style="font-size:24px;color:' + colors[k] + '">' +
          counts[k] + '</div><div class="stat-cap">' + names[k] + "</div></div>";
      }).join("") + "</div></div>";

    h += '<div class="stat-card"><div class="stat-cap" style="margin-bottom:12px">各集进度</div>';
    DB.episodes.forEach(function (ep) {
      var ws = DB.words.filter(function (w) { return w.episodeKey === ep.key; });
      var m = ws.filter(function (w) { return statusOf(keyFor(w)) === "mastered"; }).length;
      var r = ws.length ? Math.round((m / ws.length) * 100) : 0;
      h += '<div class="bar-row"><div class="bar-label">' + esc(ep.short) + "</div>" +
        '<div class="bar-track"><div class="bar-fill" style="width:' + r + '%;background:var(--b2)"></div></div>' +
        '<div class="bar-val">' + m + "/" + ws.length + "</div></div>";
    });
    h += "</div>";

    h += '<div class="stat-card"><div class="stat-cap" style="margin-bottom:12px">等级分布</div>';
    ["B2", "C1"].forEach(function (lv) {
      var n = DB.words.filter(function (w) { return w.level === lv; }).length;
      var r = Math.round((n / total) * 100);
      h += '<div class="bar-row"><div class="bar-label">' + lv + "</div>" +
        '<div class="bar-track"><div class="bar-fill" style="width:' + r + "%;background:var(--" +
        (lv === "B2" ? "b2" : "c1") + ')"></div></div>' +
        '<div class="bar-val">' + n + "</div></div>";
    });
    h += "</div>";

    h += '<div class="stat-card"><div class="stat-actions">' +
      '<button class="btn" id="act-export">导出进度 JSON</button>' +
      '<button class="btn" id="act-import">导入进度</button>' +
      '<button class="btn" id="act-reset" style="color:var(--danger)">重置全部</button>' +
      "</div></div>";

    if (DB.generated) {
      h += '<div class="stat-cap" style="text-align:center">数据生成于 ' + esc(DB.generated) + "</div>";
    }

    var body = $("#stats-body");
    body.innerHTML = h;

    $("#act-export").addEventListener("click", function () {
      var blob = new Blob([JSON.stringify(S.status, null, 2)], { type: "application/json" });
      var a = el("a");
      a.href = URL.createObjectURL(blob);
      a.download = "vocab-progress.json";
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    });
    $("#act-import").addEventListener("click", function () {
      var inp = el("input");
      inp.type = "file"; inp.accept = "application/json";
      inp.addEventListener("change", function () {
        var f = inp.files && inp.files[0];
        if (!f) return;
        var r = new FileReader();
        r.onload = function () {
          try {
            var obj = JSON.parse(r.result);
            S.status = obj && typeof obj === "object" ? obj : {};
            save(); reloadDeck(); renderList(); renderStats();
          } catch (e) { alert("导入失败：文件格式不正确"); }
        };
        r.readAsText(f);
      });
      inp.click();
    });
    $("#act-reset").addEventListener("click", function () {
      if (!confirm("清空全部学习进度？此操作不可撤销。")) return;
      S.status = {}; save(); reloadDeck(); renderList(); renderStats();
    });
  }

  /* ---------- tabs ---------- */
  $$(".tab").forEach(function (t) {
    t.addEventListener("click", function () { showTab(t.dataset.tab); });
  });

  /* ---------- swipe on card ---------- */
  (function () {
    var x0 = null, y0 = null;
    var stage = $("#card-stage");
    stage.addEventListener("touchstart", function (e) {
      x0 = e.touches[0].clientX; y0 = e.touches[0].clientY;
    }, { passive: true });
    stage.addEventListener("touchend", function (e) {
      if (x0 == null) return;
      var dx = e.changedTouches[0].clientX - x0;
      var dy = e.changedTouches[0].clientY - y0;
      if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.6) {
        if (dx < 0) { flipped ? mark("mastered") : goto(1); }
        else { flipped ? mark("learning") : goto(-1); }
      } else if (Math.abs(dy) < 12 && Math.abs(dx) < 12) {
        flip();
      }
      x0 = y0 = null;
    }, { passive: true });
  })();

  /* ---------- keyboard ---------- */
  document.addEventListener("keydown", function (e) {
    if ($("#app").dataset.view !== "cards") return;
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key === "ArrowRight") goto(1);
    else if (e.key === "ArrowLeft") goto(-1);
    else if (e.key === " ") { e.preventDefault(); flip(); }
    else if (e.key === "1") mark("learning");
    else if (e.key === "2") mark("mastered");
    else if (e.key === "3") { S.status = {}; save(); reloadDeck(); renderList(); renderStats(); }
  });

  /* ---------- init ---------- */
  applyTheme();
  fillEpisodeSelects();
  var start = currentEpisode();
  if (start) {
    S.ep = start;
    $("#filter-episode").value = start;
    $("#script-episode").value = start;
  }
  reloadDeck();
  renderList();
  renderScript();
  renderLibrary();

  if ("serviceWorker" in navigator && location.protocol.indexOf("http") === 0) {
    navigator.serviceWorker.register("sw.js").catch(function () { /* offline cache unavailable */ });
  }
})();