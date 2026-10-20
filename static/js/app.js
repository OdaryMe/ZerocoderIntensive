/* =========================================================================
   Signal — AI Job Digest
   app.js: состояние страницы, фильтры, запросы к API, отрисовка ленты,
           дайджеста, подробностей о вакансии и служебные обработчики.

   Только нативный JavaScript, без библиотек.
   ========================================================================= */

(function () {
  "use strict";

  /* --------------------------------------------------------------------
     1. Состояние и константы
     -------------------------------------------------------------------- */

  const PAGE_SIZE = 12; // сколько карточек показывать за раз
  const NEW_WINDOW_DAYS = 3; // дни, в течение которых вакансия считается новой
  const STORAGE_KEYS = {
    favorites: "signal.favorites",
    hidden: "signal.hidden",
    criteria: "signal.criteria"
  };

  const state = {
    items: [],           // данные последнего ответа сервера
    total: 0,
    facets: {},
    criteriaActive: false,
    criteria: { directions: [], skills: [], min_salary: null },
    favorites: new Set(),
    hidden: new Set(),
    limit: PAGE_SIZE
  };

  const data = window.SIGNAL_DATA || { directions: [], levels: [], formats: [], employments: [], stats: {} };

  // Справочники вида id -> подпись (для отрисовки карточек)
  const labelOf = (list, id, fallback) => {
    const found = (list || []).find((item) => item.id === id);
    return found ? found.label : fallback;
  };
  const directionById = (id) =>
    (data.directions || []).find((d) => d.id === id) ||
    { id: id || "other", label: "Другое", color: "#94a3b8", short: "Другое" };

  /* Утилиты работы с DOM и строками */

  const $ = (id) => document.getElementById(id);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));

  // Экранирование обязательно: текст вакансий приходит извне (RSS, ввод пользователя)
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));
  }

  function debounce(fn, delay) {
    let timer;
    return function () {
      clearTimeout(timer);
      timer = setTimeout(fn, delay);
    };
  }

  function readSet(key) {
    // localStorage может быть недоступен (приватный режим) — тогда просто пустой набор
    try {
      const raw = localStorage.getItem(key);
      return new Set(raw ? JSON.parse(raw) : []);
    } catch (error) {
      return new Set();
    }
  }

  function saveSet(key, set) {
    try {
      localStorage.setItem(key, JSON.stringify(Array.from(set)));
    } catch (error) { /* хранилище недоступно — работаем без сохранения */ }
  }

  function readCriteria() {
    try {
      const raw = localStorage.getItem(STORAGE_KEYS.criteria);
      if (!raw) return { directions: [], skills: [], min_salary: null };
      const parsed = JSON.parse(raw);
      return {
        directions: Array.isArray(parsed.directions) ? parsed.directions : [],
        skills: Array.isArray(parsed.skills) ? parsed.skills : [],
        min_salary: parsed.min_salary || null
      };
    } catch (error) {
      return { directions: [], skills: [], min_salary: null };
    }
  }

  function saveCriteria(criteria) {
    try {
      localStorage.setItem(STORAGE_KEYS.criteria, JSON.stringify(criteria));
    } catch (error) { /* нет доступа к хранилищу */ }
  }

  function criteriaQueryString() {
    if (!state.criteriaActive) return "";
    return JSON.stringify(state.criteria);
  }

  /* Даты и время */

  const MONTH_FORMAT = new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit" });
  const FULL_FORMAT = new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
  const FULL_TIME_FORMAT = new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit"
  });

  function toDate(value) {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function formatDate(value) {
    const date = toDate(value);
    return date ? MONTH_FORMAT.format(date) : "—";
  }

  function formatFullDate(value) {
    const date = toDate(value);
    return date ? FULL_FORMAT.format(date) : "не указана";
  }

  function formatFullDateTime(value) {
    const date = toDate(value);
    return date ? FULL_TIME_FORMAT.format(date) : "—";
  }

  // «сегодня», «вчера», «3 дня назад» — так дата обнаружения читается быстрее
  function relativeTime(value) {
    const date = toDate(value);
    if (!date) return "—";
    const days = Math.floor((Date.now() - date.getTime()) / 86400000);
    if (days <= 0) return "сегодня";
    if (days === 1) return "вчера";
    if (days < 7) return days + " дня назад";
    if (days < 30) return Math.floor(days / 7) + " нед. назад";
    return FULL_FORMAT.format(date);
  }

  /* --------------------------------------------------------------------
     2. Сбор параметров запроса (фильтры + критерии)
     -------------------------------------------------------------------- */

  function checkedValues(name) {
    return $$('input[name="' + name + '"]:checked').map((input) => input.value);
  }

  // Параметры, которые участвуют в API-запросе
  function buildParams() {
    const params = new URLSearchParams();
    const search = $("searchInput").value.trim();
    if (search) params.set("q", search.slice(0, 200));

    const sort = $("sortSelect").value;
    if (sort && sort !== "detected") params.set("sort", sort);

    const map = {
      direction: checkedValues("direction"),
      level: checkedValues("level"),
      work_format: checkedValues("work_format")
    };
    Object.keys(map).forEach((key) => {
      if (map[key].length) params.set(key, map[key].join(","));
    });

    const fields = ["country", "employment", "days", "salary_min", "salary_currency"];
    fields.forEach((name) => {
      const control = document.querySelector('[name="' + name + '"]');
      if (control && control.value) params.set(name, control.value);
    });

    if (document.querySelector('[name="new"]').checked) params.set("new", "1");
    if (document.querySelector('[name="fav"]').checked) {
      params.set("fav", "1");
    }
    if (state.favorites.size) params.set("fav_ids", Array.from(state.favorites).join(","));
    if (state.hidden.size) params.set("hide_ids", Array.from(state.hidden).join(","));

    const criteria = criteriaQueryString();
    if (criteria) params.set("criteria", criteria);

    return params;
  }

  // Параметры, которые попадают в адресную строку (для ссылок «поделиться»)
  function buildUrlParams() {
    const params = new URLSearchParams();
    const search = $("searchInput").value.trim();
    if (search) params.set("q", search.slice(0, 200));
    const sort = $("sortSelect").value;
    if (sort && sort !== "detected") params.set("sort", sort);

    const map = {
      direction: checkedValues("direction"),
      level: checkedValues("level"),
      work_format: checkedValues("work_format")
    };
    Object.keys(map).forEach((key) => {
      if (map[key].length) params.set(key, map[key].join(","));
    });

    ["country", "employment", "days", "salary_min", "salary_currency"].forEach((name) => {
      const control = document.querySelector('[name="' + name + '"]');
      if (control && control.value) params.set(name, control.value);
    });
    if (document.querySelector('[name="new"]').checked) params.set("new", "1");
    if (document.querySelector('[name="fav"]').checked) params.set("fav", "1");
    return params;
  }

  // Восстановление фильтров из адресной строки при загрузке страницы
  function restoreFromUrl() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("q")) $("searchInput").value = params.get("q");
    if (params.get("sort")) $("sortSelect").value = params.get("sort");

    ["direction", "level", "work_format"].forEach((name) => {
      const values = (params.get(name) || "").split(",").filter(Boolean);
      $$('input[name="' + name + '"]').forEach((input) => {
        input.checked = values.includes(input.value);
        input.closest(".chip")?.classList.toggle("is-checked", input.checked);
      });
    });

    ["country", "employment", "days", "salary_min", "salary_currency"].forEach((name) => {
      const value = params.get(name);
      const control = document.querySelector('[name="' + name + '"]');
      if (value && control) control.value = value;
    });

    if (params.get("new") === "1") document.querySelector('[name="new"]').checked = true;
    if (params.get("fav") === "1") document.querySelector('[name="fav"]').checked = true;
  }

  /* --------------------------------------------------------------------
     3. Загрузка вакансий
     -------------------------------------------------------------------- */

  async function refreshJobs(options) {
    const resetLimit = !options || options.resetLimit !== false;
    if (resetLimit) state.limit = PAGE_SIZE;

    const jobsList = $("jobsList");
    jobsList.setAttribute("aria-busy", "true");
    $("errorState").hidden = true;

    const query = buildParams().toString();

    try {
      const response = await fetch("/api/jobs" + (query ? "?" + query : ""));
      if (!response.ok) throw new Error("Сервер ответил ошибкой " + response.status);
      const payload = await response.json();
      if (!payload.ok) throw new Error(payload.error || "Не удалось получить вакансии");

      state.items = payload.items;
      state.total = payload.total;
      state.facets = payload.facets || {};
      state.criteriaActive = payload.criteria_active;

      renderJobs();
      renderResultsCount();
      renderFacetCounts();
      renderCountryOptions();
      renderActiveFilters();
      renderFilterBadges();

      $("exportLink").setAttribute("href", "/api/export.csv" + (query ? "?" + query : ""));
      updateUrl();
    } catch (error) {
      $("errorMessage").textContent =
        "Не удалось загрузить вакансии: " + error.message + ". Проверьте, что приложение запущено.";
      $("errorState").hidden = false;
      jobsList.innerHTML = "";
      $("emptyState").hidden = true;
    } finally {
      jobsList.setAttribute("aria-busy", "false");
    }
  }

  function updateUrl() {
    const query = buildUrlParams().toString();
    const target = window.location.pathname + (query ? "?" + query : "") + window.location.hash;
    window.history.replaceState(null, "", target);
  }

  /* --------------------------------------------------------------------
     4. Отрисовка ленты вакансий
     -------------------------------------------------------------------- */

  function renderJobs() {
    const visible = state.items.slice(0, state.limit);
    $("jobsList").innerHTML = visible.map(jobCardHtml).join("");
    $("emptyState").hidden = state.total !== 0;
    $("loadMoreBtn").hidden = state.total <= state.limit;
  }

  function jobCardHtml(job, index) {
    const direction = directionById(job.direction);
    const isFavorite = state.favorites.has(job.id);
    const fresh = Boolean(job.is_new);
    const hasSalary = job.salary_text && job.salary_text !== "Не указана";

    const tags = [
      '<span class="tag tag--direction">' + esc(job.direction_label || direction.label) + "</span>",
      job.is_demo ? '<span class="tag tag--demo">ДЕМО</span>' : "",
      fresh ? '<span class="tag tag--new">NEW</span>' : "",
      '<span class="job-card__level mono">' + esc(levelLabel(job.level)) + "</span>"
    ].filter(Boolean).join("");

    const skills = (job.skills || []).slice(0, 6)
      .map((skill) => '<li class="skill">' + esc(skill) + "</li>").join("");

    const metaBits = [
      esc(job.company || "Компания не указана"),
      esc(job.country && job.country !== "none" ? job.country : "география не указана"),
      esc(formatLabel(job.work_format, data.formats))
    ].filter(Boolean);

    const relevanceHtml = job.relevance ? relevanceBlockHtml(job.relevance, direction.color) : "";

    const linkHtml = job.url
      ? '<a class="action-btn" href="' + esc(job.url) + '" target="_blank" rel="noopener noreferrer">Оригинал ↗</a>'
      : '<span class="action-btn action-btn--muted" title="У тестовой записи нет настоящей ссылки">Ссылки нет</span>';

    return (
      '<article class="job-card' + (fresh ? " job-card--fresh" : "") + '"' +
      ' style="--accent:' + esc(direction.color) + ";--i:" + index + '"' +
      ' data-id="' + esc(job.id) + '">' +

        '<div class="job-card__main">' +
          '<div class="job-card__tags">' + tags + "</div>" +
          '<h3 class="job-card__title">' +
            '<button type="button" data-action="open" data-id="' + esc(job.id) + '">' +
              esc(job.title) +
            "</button>" +
          "</h3>" +
          '<p class="job-card__company">' + metaBits.join(' <span class="sep">·</span> ') + "</p>" +
          '<p class="job-card__desc">' + esc(job.description || "") + "</p>" +
          (skills ? '<ul class="job-card__skills">' + skills + "</ul>" : "") +
        "</div>" +

        '<div class="job-card__side">' +
          "<div>" +
            '<span class="salary__label">зарплата</span>' +
            '<span class="salary__value' + (hasSalary ? "" : " is-empty") + '">' +
              esc(job.salary_text || "Не указана") +
            "</span>" +
          "</div>" +
          '<dl class="job-meta">' +
            "<div><dt>публикация</dt><dd>" + esc(formatDate(job.published_at)) + "</dd></div>" +
            "<div><dt>обнаружена</dt><dd>" + esc(relativeTime(job.detected_at)) + "</dd></div>" +
          "</dl>" +
          relevanceHtml +
          '<div class="job-card__actions">' +
            '<button type="button" class="action-btn' + (isFavorite ? " is-active" : "") + '"' +
              ' data-action="fav" data-id="' + esc(job.id) + '">' +
              (isFavorite ? "★ В избранном" : "☆ В избранное") +
            "</button>" +
            '<button type="button" class="action-btn" data-action="hide" data-id="' + esc(job.id) + '">' +
              "✕ Скрыть" +
            "</button>" +
            '<button type="button" class="action-btn action-btn--primary" data-action="open" data-id="' +
              esc(job.id) + '">Подробнее</button>' +
            linkHtml +
          "</div>" +
        "</div>" +
      "</article>"
    );
  }

  function relevanceBlockHtml(relevanceInfo, accent) {
    return (
      '<div class="relevance" style="--accent:' + esc(accent) + '">' +
        '<div class="ring" style="--p:' + Number(relevanceInfo.score) + '">' +
          "<span>" + Number(relevanceInfo.score) + "%</span>" +
        "</div>" +
        '<span class="relevance__text">соответствие<br>критериям</span>' +
      "</div>"
    );
  }

  function levelLabel(levelId) {
    if (!levelId || levelId === "none") return "уровень не указан";
    return labelOf(data.levels, levelId, levelId);
  }

  function formatLabel(formatId, list) {
    if (!formatId || formatId === "none") return "формат не указан";
    return labelOf(list, formatId, formatId);
  }

  function renderResultsCount() {
    const totalInBase = data.stats ? data.stats.total : state.total;
    const filtersActive = hasActiveFilters();
    const suffix = filtersActive ? " из " + totalInBase + " в базе" : " в базе";
    $("resultsCount").innerHTML =
      "<strong>" + state.total + "</strong> " + pluralJobs(state.total) + esc(suffix);
  }

  function pluralJobs(count) {
    const mod10 = count % 10;
    const mod100 = count % 100;
    if (mod10 === 1 && mod100 !== 11) return "вакансия";
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "вакансии";
    return "вакансий";
  }

  /* --------------------------------------------------------------------
     5. Счётчики фильтров, активные фильтры, плашки
     -------------------------------------------------------------------- */

  function renderFacetCounts() {
    $$("[data-count-for]").forEach((node) => {
      const parts = node.getAttribute("data-count-for").split(":");
      const field = parts[0];
      const value = parts[1];
      const count = (state.facets[field] || {})[value] || 0;
      node.textContent = count;
      node.style.opacity = count === 0 ? "0.45" : "1";
    });
  }

  function renderCountryOptions() {
    const select = $("countrySelect");
    if (!select) return;
    const current = select.value;
    const counts = state.facets.country || {};
    const values = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);

    const options = ['<option value="">Все страны</option>'];
    values.forEach((value) => {
      const label = value === "none" ? "Не указана" : value;
      options.push(
        '<option value="' + esc(value) + '">' + esc(label) + " (" + counts[value] + ")</option>"
      );
    });
    select.innerHTML = options.join("");
    // Сохраняем выбор пользователя, даже если вариантов сейчас нет
    if (current && !values.includes(current)) {
      select.insertAdjacentHTML("beforeend", '<option value="' + esc(current) + '">' + esc(current) + "</option>");
    }
    if (current) select.value = current;
  }

  function activeFilterList() {
    const list = [];
    const search = $("searchInput").value.trim();
    if (search) list.push({ key: "q", label: "поиск: " + search });

    checkedValues("direction").forEach((id) =>
      list.push({ key: "direction:" + id, label: directionById(id).label }));
    checkedValues("level").forEach((id) =>
      list.push({ key: "level:" + id, label: "уровень: " + labelOf(data.levels, id, id) }));
    checkedValues("work_format").forEach((id) =>
      list.push({ key: "work_format:" + id, label: formatLabel(id, data.formats) }));

    const controls = [
      { name: "country", label: "страна" },
      { name: "employment", label: "занятость" },
      { name: "days", label: "период публикации" },
      { name: "salary_min", label: "зарплата от" },
      { name: "salary_currency", label: "валюта" }
    ];
    controls.forEach((item) => {
      const control = document.querySelector('[name="' + item.name + '"]');
      if (control && control.value) list.push({ key: item.name, label: item.label + ": " + control.value });
    });

    if (document.querySelector('[name="new"]').checked) list.push({ key: "new", label: "только новые" });
    if (document.querySelector('[name="fav"]').checked) list.push({ key: "fav", label: "только избранное" });
    if (state.criteriaActive) list.push({ key: "criteria", label: "мои критерии" });
    return list;
  }

  function renderActiveFilters() {
    const active = activeFilterList();
    $("activeFilters").innerHTML = active.map((item, index) =>
      '<span class="afilter" style="animation-delay:' + (index * 30) + 'ms">' +
        esc(item.label) +
        '<button type="button" data-clear="' + esc(item.key) + '" aria-label="Убрать фильтр">✕</button>' +
      "</span>"
    ).join("");
    $("resetBtn").hidden = active.length === 0;
  }

  function renderFilterBadges() {
    const count = activeFilterList().length;
    const badge = $("filtersCount");
    badge.hidden = count === 0;
    badge.textContent = String(count);

    const favCount = $("favCounter");
    if (favCount) favCount.textContent = "(" + state.favorites.size + ")";

    const badgeCriteria = $("criteriaBadge");
    if (badgeCriteria) {
      badgeCriteria.textContent = state.criteriaActive ? "вкл" : "выкл";
      badgeCriteria.classList.toggle("pill--on", state.criteriaActive);
      badgeCriteria.classList.toggle("pill--off", !state.criteriaActive);
    }

    $("showHiddenBtn").hidden = state.hidden.size === 0;
  }

  function hasActiveFilters() {
    return activeFilterList().length > 0;
  }

  /* Удаление конкретного фильтра крестиком */
  function clearFilter(key) {
    if (key === "q") $("searchInput").value = "";
    else if (key === "new") document.querySelector('[name="new"]').checked = false;
    else if (key === "fav") document.querySelector('[name="fav"]').checked = false;
    else if (key === "criteria") clearCriteria(false);
    else if (key.indexOf(":") !== -1) {
      const parts = key.split(":");
      const input = document.querySelector('input[name="' + parts[0] + '"][value="' + parts[1] + '"]');
      if (input) {
        input.checked = false;
        input.closest(".chip")?.classList.remove("is-checked");
      }
    } else {
      const control = document.querySelector('[name="' + key + '"]');
      if (control) {
        if (control.type === "checkbox") control.checked = false;
        else control.value = "";
      }
    }
    refreshJobs();
  }

  function resetFilters() {
    $("searchInput").value = "";
    $("sortSelect").value = "detected";
    $$('input[type="checkbox"]', $("filtersPanel")).forEach((input) => {
      // Чекбоксы критериев сбрасываем отдельно, через clearCriteria
      if (input.name === "criteria_direction") return;
      input.checked = false;
      input.closest(".chip")?.classList.remove("is-checked");
    });
    $$("select", $("filtersPanel")).forEach((select) => { select.value = ""; });
    $$('input[type="number"]', $("filtersPanel")).forEach((input) => {
      if (input.id === "criteriaSkills" || input.id === "criteriaSalary") return;
      input.value = "";
    });
    clearCriteria(false);
    $("digestPeriod").value = "7";
    refreshJobs();
    loadDigest();
    toast("Фильтры сброшены");
  }

  /* --------------------------------------------------------------------
     6. Избранное, скрытие
     -------------------------------------------------------------------- */

  function toggleFavorite(id, button) {
    const adding = !state.favorites.has(id);
    if (adding) state.favorites.add(id);
    else state.favorites.delete(id);
    saveSet(STORAGE_KEYS.favorites, state.favorites);

    if (button) {
      button.classList.toggle("is-active", adding);
      button.textContent = adding ? "★ В избранном" : "☆ В избранное";
    }
    renderFilterBadges();
    toast(adding ? "Вакансия сохранена в избранное" : "Вакансия удалена из избранного");

    // Если включён фильтр «только избранное» — выдача должна измениться сразу
    if (document.querySelector('[name="fav"]').checked) refreshJobs();
  }

  function hideJob(id, card) {
    state.hidden.add(id);
    saveSet(STORAGE_KEYS.hidden, state.hidden);

    const finish = () => refreshJobs();
    if (card) {
      card.classList.add("is-removing");
      setTimeout(finish, 260);
    } else {
      finish();
    }

    toast("Вакансия скрыта из ленты", "Вернуть", () => {
      state.hidden.delete(id);
      saveSet(STORAGE_KEYS.hidden, state.hidden);
      refreshJobs();
    });
  }

  /* --------------------------------------------------------------------
     7. Панель подробностей о вакансии
     -------------------------------------------------------------------- */

  let lastFocusedElement = null;

  async function openDrawer(id) {
    const drawer = $("jobDrawer");
    lastFocusedElement = document.activeElement;
    drawer.hidden = false;
    $("drawerBody").innerHTML = '<p class="loading-line">Загружаю подробности…</p>';
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => drawer.classList.add("is-open"));

    try {
      const criteria = criteriaQueryString();
      const url = "/api/jobs/" + encodeURIComponent(id) +
        (criteria ? "?criteria=" + encodeURIComponent(criteria) : "");
      const response = await fetch(url);
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || "Вакансия не найдена");
      $("drawerBody").innerHTML = detailHtml(payload.job);
      const closeBtn = $("drawerBody").parentElement.querySelector("[data-close-drawer]");
      if (closeBtn) closeBtn.focus();
    } catch (error) {
      $("drawerBody").innerHTML =
        '<div class="empty-state empty-state--error"><h3>Не удалось открыть вакансию</h3><p>' +
        esc(error.message) + "</p></div>";
    }
  }

  function closeDrawer() {
    const drawer = $("jobDrawer");
    drawer.classList.remove("is-open");
    document.body.style.overflow = "";
    setTimeout(() => { drawer.hidden = true; }, 360);
    if (lastFocusedElement && lastFocusedElement.focus) lastFocusedElement.focus();
  }

  function detailHtml(job) {
    const direction = directionById(job.direction);
    const isFavorite = state.favorites.has(job.id);
    const hasSalary = job.salary_text && job.salary_text !== "Не указана";

    const skills = (job.skills || []).map((skill) =>
      '<li class="skill">' + esc(skill) + "</li>").join("");

    const relevance = job.relevance
      ? '<div class="relevance-box">' +
          '<div class="relevance-box__head">' +
            '<div class="ring" style="--accent:' + esc(direction.color) + ";--p:" +
              Number(job.relevance.score) + '"><span>' + Number(job.relevance.score) + "%</span></div>" +
            '<span class="relevance-box__score">Соответствие вашим критериям</span>' +
          "</div>" +
          "<ul>" + job.relevance.reasons.map((reason) => "<li>" + esc(reason) + "</li>").join("") + "</ul>" +
        "</div>"
      : "";

    const link = job.url
      ? '<a class="action-btn action-btn--primary" href="' + esc(job.url) +
        '" target="_blank" rel="noopener noreferrer">Открыть оригинал ↗</a>'
      : '<span class="action-btn action-btn--muted">Ссылка недоступна — тестовая запись</span>';

    return (
      '<div class="detail__tags">' +
        '<span class="tag tag--direction" style="--accent:' + esc(direction.color) + '">' +
          esc(job.direction_label) + "</span>" +
        (job.is_demo ? '<span class="tag tag--demo">ДЕМО</span>' : "") +
        (job.is_new ? '<span class="tag tag--new">NEW</span>' : "") +
        '<span class="job-card__level mono">' + esc(levelLabel(job.level)) + "</span>" +
        '<span class="job-card__level mono">' + esc(formatLabel(job.work_format, data.formats)) + "</span>" +
        '<span class="job-card__level mono">' + esc(formatLabel(job.employment, data.employments)) + "</span>" +
      "</div>" +

      '<h3 class="detail__title" id="drawerTitle">' + esc(job.title) + "</h3>" +
      '<p class="detail__company">' + esc(job.company || "Компания не указана") +
        (job.location ? " · " + esc(job.location) : "") +
        (job.country && job.country !== "none" ? " · " + esc(job.country) : "") +
      "</p>" +

      '<div class="detail__salary' + (hasSalary ? "" : " is-empty") + '">' +
        (hasSalary ? esc(job.salary_text) : "Зарплата не указана — работодатель не опубликовал вилку") +
      "</div>" +

      relevance +

      '<section class="detail-section"><h4>Описание и обязанности</h4><p>' +
        esc(job.description || "Описание не опубликовано.") + "</p></section>" +

      (skills
        ? '<section class="detail-section"><h4>Навыки</h4><ul class="job-card__skills">' + skills + "</ul></section>"
        : "") +

      '<section class="detail-section"><h4>Даты</h4>' +
        '<div class="detail__dates">' +
          '<div class="detail__date"><span>опубликована</span><strong>' +
            esc(formatFullDate(job.published_at)) + "</strong></div>" +
          '<div class="detail__date"><span>обнаружена системой</span><strong>' +
            esc(formatFullDateTime(job.detected_at)) + "</strong></div>" +
          '<div class="detail__date"><span>последняя проверка</span><strong>' +
            esc(formatFullDateTime(job.source_status || job.checked_at)) + "</strong></div>" +
        "</div>" +
      "</section>" +

      '<section class="detail-section"><h4>Источник</h4>' +
        "<p>Источник: <code>" + esc(job.source) + "</code>" +
        " · идентификатор: <code>" + esc(job.source_id) + "</code><br>" +
        (job.is_demo
          ? "Это демонстрационная запись: она создана для показа интерфейса и не является настоящей вакансией."
          : "Запись получена из внешнего источника.") +
        "</p></section>" +

      '<div class="detail__actions">' +
        '<button type="button" class="action-btn' + (isFavorite ? " is-active" : "") +
          '" data-detail-action="fav" data-id="' + esc(job.id) + '">' +
          (isFavorite ? "★ В избранном" : "☆ В избранное") + "</button>" +
        '<button type="button" class="action-btn" data-detail-action="hide" data-id="' +
          esc(job.id) + '">✕ Скрыть</button>' +
        link +
      "</div>"
    );
  }

  /* --------------------------------------------------------------------
     8. Дайджест
     -------------------------------------------------------------------- */

  async function loadDigest() {
    const days = $("digestPeriod").value;
    $("digestGrid").setAttribute("aria-busy", "true");
    try {
      const criteria = criteriaQueryString();
      const url = "/api/digest?days=" + encodeURIComponent(days) +
        (criteria ? "&criteria=" + encodeURIComponent(criteria) : "");
      const response = await fetch(url);
      const payload = await response.json();
      if (!payload.ok) throw new Error(payload.error || "Ошибка дайджеста");
      renderDigest(payload.digest);
    } catch (error) {
      renderDigestError(error.message);
    } finally {
      $("digestGrid").setAttribute("aria-busy", "false");
    }
  }

  function renderDigest(digest) {
    const periodLabel = digest.days === 1 ? "за 24 часа" : "за " + digest.days + " дней";

    // Первый блок: новые вакансии крупной цифрой
    $("digestHero").innerHTML =
      '<p class="eyebrow">Новых вакансий ' + esc(periodLabel) + "</p>" +
      '<p class="digest-hero__value">' + digest.new_count + "</p>" +
      '<p class="digest-hero__caption">' +
        (digest.empty_period
          ? "В этом периоде появиться не успело — попробуйте более длинный период."
          : "обнаружено системой " + periodLabel + " · опубликовано за период: " + digest.published_count) +
      "</p>" +
      '<div class="digest-hero__split">' +
        "<span>всего в базе <strong>" + digest.total_jobs + "</strong></span>" +
        "<span>с зарплатой <strong>" + digest.salary_coverage.with_salary + "</strong></span>" +
        "<span>без зарплаты <strong>" + digest.salary_coverage.without_salary + "</strong></span>" +
      "</div>";

    // Частые навыки — полосы частоты
    if (!digest.top_skills.length) {
      $("digestSkills").innerHTML =
        '<p class="eyebrow">Частые навыки</p><p class="digest-empty">За выбранный период нет данных о навыках.</p>';
    } else {
      const max = digest.top_skills[0].count;
      const rows = digest.top_skills.map((item) => {
        const width = Math.max(8, Math.round((item.count / max) * 100));
        return (
          '<div class="bar-item">' +
            '<div class="bar-item__head"><span>' + esc(item.name) + "</span><strong>" +
              item.count + "×</strong></div>" +
            '<div class="bar"><span data-width="' + width + '%"></span></div>' +
          "</div>"
        );
      }).join("");
      $("digestSkills").innerHTML = '<p class="eyebrow">Частые навыки</p><div class="bar-list">' + rows + "</div>";
      // Полосы анимируемся после вставки в DOM
      requestAnimationFrame(() => {
        $$("#digestSkills .bar span").forEach((bar) => {
          bar.style.width = bar.getAttribute("data-width");
        });
      });
    }

    // Направления — клик включает соответствующий фильтр
    if (!digest.top_directions.length) {
      $("digestDirections").innerHTML =
        '<p class="eyebrow">Востребованные направления</p><p class="digest-empty">Нет данных за период.</p>';
    } else {
      const rows = digest.top_directions.slice(0, 6).map((item) =>
        '<button type="button" class="dir-item" data-direction="' + esc(item.id) + '">' +
          '<span class="dot" style="--dot:' + esc(item.color) + '"></span>' +
          esc(item.label) + "<strong>" + item.count + "</strong>" +
        "</button>"
      ).join("");
      $("digestDirections").innerHTML =
        '<p class="eyebrow">Востребованные направления</p><div class="dir-list">' + rows + "</div>";
    }

    // Зарплатные диапазоны
    if (!digest.salary_ranges.length) {
      $("digestSalaries").innerHTML =
        '<p class="eyebrow">Зарплатные диапазоны</p>' +
        '<p class="digest-empty">В этом периоде не опубликована ни одна вилка. Signal не придумывает зарплаты — показывает только то, что указано в вакансии.</p>';
    } else {
      const rows = digest.salary_ranges.map((item) =>
        '<div class="salary-row"><span>' + esc(item.text) + "</span><span>×" + item.count + "</span></div>"
      ).join("");
      $("digestSalaries").innerHTML =
        '<p class="eyebrow">Зарплатные диапазоны</p><div class="salary-rows">' + rows + "</div>";
    }

    // Недавно обнаруженные вакансии
    if (!digest.interesting.length) {
      $("digestInteresting").innerHTML =
        '<p class="eyebrow">Обнаружены недавно</p><p class="digest-empty">Свежих записей за период нет.</p>';
    } else {
      const rows = digest.interesting.map((item) => {
        const direction = directionById(item.direction);
        const score = item.relevance
          ? '<span class="interesting-item__score">' + item.relevance.score + "%</span>"
          : '<span class="interesting-item__score" style="color:var(--text-mute)">' +
            esc(relativeTime(item.detected_at)) + "</span>";
        return (
          '<button type="button" class="interesting-item" data-job="' + esc(item.id) + '">' +
            '<span class="dot" style="--dot:' + esc(direction.color) + '"></span>' +
            '<span class="interesting-item__main">' +
              '<span class="interesting-item__title">' + esc(item.title) + "</span>" +
              '<span class="interesting-item__meta">' + esc(item.company || "—") +
                (item.is_demo ? " · ДЕМО" : "") + " · " + esc(item.salary_text) + "</span>" +
            "</span>" + score +
          "</button>"
        );
      }).join("");
      $("digestInteresting").innerHTML =
        '<p class="eyebrow">Обнаружены недавно</p><div class="interesting-list">' + rows + "</div>";
    }
  }

  function renderDigestError(message) {
    $("digestHero").innerHTML =
      '<p class="eyebrow">Новых вакансий</p><p class="digest-empty">Ошибка загрузки дайджеста: ' +
      esc(message) + "</p>";
  }

  async function generateAiSummary() {
    const button = $("aiBtn");
    const result = $("aiResult");
    if (!button || !result) return;

    button.disabled = true;
    button.textContent = "Считаю…";
    result.hidden = false;
    result.classList.remove("is-error");
    result.innerHTML = '<span class="loading-line">Модель формирует резюме…</span>';

    try {
      const response = await fetch("/api/ai-summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          days: Number($("digestPeriod").value),
          criteria: state.criteriaActive ? state.criteria : null
        })
      });
      const payload = await response.json();
      if (payload.ok && payload.result.ok) {
        result.textContent = payload.result.text;
      } else {
        result.classList.add("is-error");
        result.textContent = (payload.result && payload.result.error) || "Не удалось получить резюме.";
      }
    } catch (error) {
      result.classList.add("is-error");
      result.textContent = "Сервис недоступен: " + error.message;
    } finally {
      button.disabled = false;
      button.textContent = "Сформировать резюме";
    }
  }

  /* --------------------------------------------------------------------
     9. Обновление данных из источников
     -------------------------------------------------------------------- */

  async function runUpdate() {
    const buttons = [$("refreshBtn"), $("refreshBtnSecondary")].filter(Boolean);
    buttons.forEach((button) => { button.disabled = true; });
    const originalText = $("refreshBtn").textContent;
    $("refreshBtn").textContent = "Обновляю…";

    try {
      const response = await fetch("/api/update", { method: "POST" });
      const payload = await response.json();
      if (!payload.status) throw new Error("Сервер не вернул статус");

      renderStatus(payload.status, payload.status_label);

      const failed = payload.status.sources.filter((source) => !source.ok);
      const added = payload.status.sources.reduce((sum, source) => sum + (source.added || 0), 0);
      if (failed.length) {
        toast("Обновление частично не прошло: " + failed.length + " источник(ов) с ошибкой", "К ошибкам", () => {
          document.getElementById("sources").scrollIntoView({ behavior: "smooth" });
        });
      } else if (added) {
        toast("Обновлено: новых вакансий — " + added);
      } else {
        toast("Источники проверены, новых записей нет");
      }

      await Promise.all([refreshJobs(), loadDigest()]);
    } catch (error) {
      toast("Не удалось обновить данные: " + error.message);
    } finally {
      buttons.forEach((button) => { button.disabled = false; });
      $("refreshBtn").textContent = originalText;
    }
  }

  // Обновляет блок «Статус данных» и подпись в шапке после обновления
  function renderStatus(status, statusLabel) {
    $$(".status-time").forEach((node) => { node.textContent = statusLabel || "обновлено"; });
    const modeNode = document.querySelector(".header__status .status-mode");
    if (modeNode) modeNode.textContent = status.mode === "demo+rss" ? "ДЕМО + RSS" : "ДЕМО";

    const list = $("sourceList");
    if (!list) return;

    const rows = (status.sources || []).map((source) =>
      '<li class="source-item ' + (source.ok ? "is-ok" : "is-error") + '">' +
        '<span class="source-item__dot"></span>' +
        '<div class="source-item__body">' +
          '<p class="source-item__name">' + esc(source.name) +
            (source.kind === "demo" ? ' <span class="tag tag--demo">ДЕМО</span>' : "") + "</p>" +
          '<p class="source-item__meta mono">' +
            (source.ok
              ? "проверено: " + source.checked + " · новых: " + source.added +
                (source.note ? " · " + esc(source.note) : "")
              : "ошибка: " + esc(source.error || "неизвестная ошибка")) +
          "</p>" +
        "</div>" +
      "</li>"
    );
    list.innerHTML = rows.join("");
  }

  /* --------------------------------------------------------------------
     10. Мои критерии (оценка соответствия)
     -------------------------------------------------------------------- */

  function syncCriteriaUi() {
    $$('input[name="criteria_direction"]').forEach((input) => {
      input.checked = state.criteria.directions.includes(input.value);
      input.closest(".chip")?.classList.toggle("is-checked", input.checked);
    });
    $("criteriaSkills").value = state.criteria.skills.join(", ");
    $("criteriaSalary").value = state.criteria.min_salary || "";
    renderFilterBadges();
  }

  function applyCriteriaFromUi() {
    const directions = $$('input[name="criteria_direction"]:checked').map((input) => input.value);
    const skillsRaw = $("criteriaSkills").value.split(",").map((item) => item.trim()).filter(Boolean).slice(0, 20);
    const salaryRaw = $("criteriaSalary").value;
    const minSalary = salaryRaw ? Math.max(0, parseInt(salaryRaw, 10) || 0) : null;

    state.criteria = { directions: directions, skills: skillsRaw, min_salary: minSalary };
    state.criteriaActive = directions.length > 0 || skillsRaw.length > 0 || minSalary !== null;
    saveCriteria(state.criteria);

    refreshJobs();
    loadDigest();
    toast(state.criteriaActive
      ? "Критерии применены — оценка соответствия обновилась"
      : "Критерии очищены");
  }

  function clearCriteria(reload) {
    state.criteria = { directions: [], skills: [], min_salary: null };
    state.criteriaActive = false;
    saveCriteria(state.criteria);
    syncCriteriaUi();
    if (reload !== false) {
      refreshJobs();
      loadDigest();
    }
  }

  /* --------------------------------------------------------------------
     11. Уведомления
     -------------------------------------------------------------------- */

  let toastTimer = null;

  function toast(message, actionLabel, actionFn) {
    const node = $("toast");
    node.innerHTML = "<span>" + esc(message) + "</span>";
    if (actionLabel) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = actionLabel;
      button.addEventListener("click", () => {
        hideToast();
        if (actionFn) actionFn();
      });
      node.appendChild(button);
    }
    node.hidden = false;
    requestAnimationFrame(() => node.classList.add("is-visible"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(hideToast, actionLabel ? 6000 : 3400);
  }

  function hideToast() {
    const node = $("toast");
    node.classList.remove("is-visible");
    setTimeout(() => { node.hidden = true; }, 260);
  }

  /* --------------------------------------------------------------------
     12. Инициализация и обработчики событий
     -------------------------------------------------------------------- */

  function bindEvents() {
    /* Поиск с задержкой, чтобы не гореть запросами на каждую букву */
    $("searchInput").addEventListener("input", debounce(() => refreshJobs(), 300));

    /* Сортировка */
    $("sortSelect").addEventListener("change", () => refreshJobs());

    /* Все фильтры в боковой панели */
    $("filtersPanel").addEventListener("change", (event) => {
      const name = event.target.name || "";
      if (!name || name.startsWith("criteria_")) return;
      // Чипы: подсвечиваем выбранные вручную (запасной вариант для :has)
      if (event.target.type === "checkbox") {
        event.target.closest(".chip")?.classList.toggle("is-checked", event.target.checked);
      }
      refreshJobs();
    });

    /* Кнопки сброса (их три — все ведут к одному поведению) */
    ["resetBtn", "resetFiltersSide", "emptyResetBtn"].forEach((id) => {
      const button = $(id);
      if (button) button.addEventListener("click", resetFilters);
    });

    /* Показать скрытые */
    $("showHiddenBtn").addEventListener("click", () => {
      state.hidden.clear();
      saveSet(STORAGE_KEYS.hidden, state.hidden);
      refreshJobs();
      toast("Скрытые вакансии возвращены в ленту");
    });

    /* Удаление отдельного фильтра крестиком */
    $("activeFilters").addEventListener("click", (event) => {
      const button = event.target.closest("[data-clear]");
      if (button) clearFilter(button.getAttribute("data-clear"));
    });

    /* Подгрузка следующей порции карточек */
    $("loadMoreBtn").addEventListener("click", () => {
      state.limit += PAGE_SIZE;
      renderJobs();
    });

    $("retryBtn").addEventListener("click", () => refreshJobs());

    /* Мобильная панель фильтров */
    $("filtersToggle").addEventListener("click", () => {
      const panel = $("filtersPanel");
      const open = panel.classList.toggle("is-open");
      $("filtersToggle").setAttribute("aria-expanded", String(open));
      if (open) panel.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    /* Обновление данных из источников */
    [$("refreshBtn"), $("refreshBtnSecondary")].forEach((button) => {
      if (button) button.addEventListener("click", runUpdate);
    });

    /* Действия внутри карточек делегированием — один обработчик на список */
    $("jobsList").addEventListener("click", (event) => {
      const button = event.target.closest("[data-action]");
      if (!button) return;
      const id = button.getAttribute("data-id");
      const action = button.getAttribute("data-action");
      if (action === "open") openDrawer(id);
      else if (action === "fav") toggleFavorite(id, button);
      else if (action === "hide") hideJob(id, button.closest(".job-card"));
    });

    /* Действия внутри панели подробностей */
    $("drawerBody").addEventListener("click", (event) => {
      const button = event.target.closest("[data-detail-action]");
      if (!button) return;
      const id = button.getAttribute("data-id");
      const action = button.getAttribute("data-detail-action");
      if (action === "fav") {
        toggleFavorite(id, null);
        button.classList.toggle("is-active", state.favorites.has(id));
        button.textContent = state.favorites.has(id) ? "★ В избранном" : "☆ В избранное";
      } else if (action === "hide") {
        state.hidden.add(id);
        saveSet(STORAGE_KEYS.hidden, state.hidden);
        closeDrawer();
        setTimeout(() => refreshJobs(), 200);
        toast("Вакансия скрыта из ленты", "Вернуть", () => {
          state.hidden.delete(id);
          saveSet(STORAGE_KEYS.hidden, state.hidden);
          refreshJobs();
        });
      }
    });

    /* Закрытие панели подробностей */
    $$("[data-close-drawer]").forEach((node) => node.addEventListener("click", closeDrawer));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !$("jobDrawer").hidden) closeDrawer();
    });

    /* Критерии */
    $("criteriaApply").addEventListener("click", applyCriteriaFromUi);
    $("criteriaClear").addEventListener("click", () => clearCriteria(true));
    $("criteriaSkills").addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); applyCriteriaFromUi(); }
    });

    /* Период дайджеста */
    $("digestPeriod").addEventListener("change", loadDigest);

    /* AI-резюме (кнопка есть только когда сервис настроен) */
    if ($("aiBtn")) $("aiBtn").addEventListener("click", generateAiSummary);

    /* Клик по направлению в дайджесте — быстрый фильтр ленты */
    $("digestDirections").addEventListener("click", (event) => {
      const button = event.target.closest("[data-direction]");
      if (!button) return;
      const value = button.getAttribute("data-direction");
      $$('input[name="direction"]').forEach((input) => {
        input.checked = input.value === value;
        input.closest(".chip")?.classList.toggle("is-checked", input.checked);
      });
      document.getElementById("jobs").scrollIntoView({ behavior: "smooth" });
      refreshJobs();
      toast("Фильтр: " + directionById(value).label);
    });

    /* Открытие вакансии из дайджеста */
    $("digestInteresting").addEventListener("click", (event) => {
      const button = event.target.closest("[data-job]");
      if (button) openDrawer(button.getAttribute("data-job"));
    });

    /* Шапка: подложка при прокрутке + мобильное меню */
    const onScroll = () => {
      $("siteHeader").classList.toggle("is-scrolled", window.scrollY > 8);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    $("burgerBtn").addEventListener("click", () => {
      const menu = $("mobileMenu");
      const open = menu.hidden;
      menu.hidden = !open;
      $("burgerBtn").setAttribute("aria-expanded", String(open));
    });
    $$("#mobileMenu a").forEach((link) => link.addEventListener("click", () => {
      $("mobileMenu").hidden = true;
      $("burgerBtn").setAttribute("aria-expanded", "false");
    }));
  }

  function init() {
    state.favorites = readSet(STORAGE_KEYS.favorites);
    state.hidden = readSet(STORAGE_KEYS.hidden);
    state.criteria = readCriteria();
    state.criteriaActive =
      state.criteria.directions.length > 0 ||
      state.criteria.skills.length > 0 ||
      Boolean(state.criteria.min_salary);

    syncCriteriaUi();
    restoreFromUrl();
    bindEvents();
    refreshJobs();
    loadDigest();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
