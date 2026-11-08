/* Страница «Аналитика»: периоды 7/30/90, фильтр по тегам, графики, дайджест.
   Данные берутся из /api/analytics и /api/digest (FR-32, FR-34, FR-36). */
(function () {
  'use strict';

  var state = { period: 7, tags: [] };

  function qs(params) {
    var parts = [];
    Object.keys(params).forEach(function (key) {
      var value = params[key];
      if (Array.isArray(value)) {
        value.forEach(function (v) { if (v) parts.push(key + '=' + encodeURIComponent(v)); });
      } else if (value !== '' && value != null) {
        parts.push(key + '=' + encodeURIComponent(value));
      }
    });
    return parts.length ? '?' + parts.join('&') : '';
  }

  function setLoading(isLoading) {
    document.querySelectorAll('#chart-card-1, #chart-card-2').forEach(function (card) {
      card.style.opacity = isLoading ? '0.55' : '1';
    });
  }

  function renderCharts(data) {
    var moodCard = document.getElementById('chart-card-1');
    var stressCard = document.getElementById('chart-card-2');
    var empty = document.getElementById('analytics-empty');

    if (data.empty) {
      moodCard.hidden = true;
      stressCard.hidden = true;
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    moodCard.hidden = false;
    stressCard.hidden = false;

    window.BalansCharts.renderMood(document.getElementById('chart-mood'), data.days);
    window.BalansCharts.renderStress(document.getElementById('chart-stress'), data.days);
  }

  function fillDigest(blockId, digest) {
    var block = document.getElementById(blockId);
    if (!block) return;
    block.hidden = false;
    function set(key, value) {
      var node = block.querySelector('[data-k="' + key + '"]');
      if (node) node.textContent = value;
    }
    set('avg_mood', digest.current.avg_mood == null ? '—' : digest.current.avg_mood.toFixed(1) + ' / 5');
    set('avg_stress', digest.current.avg_stress == null ? '—' : digest.current.avg_stress.toFixed(1) + ' / 10');
    set('completion', digest.current.completion_rate_text || '—');
    set('days', digest.current.days_with_entries + ' из ' + digest.length_days);
    var trend = block.querySelector('.trend');
    set('trend', digest.trend.text);
    if (trend) {
      trend.className = 'trend ' + (digest.trend.direction || '');
    }
    var insufficient = document.getElementById('digest-insufficient');
    if (digest.trend.direction === 'unknown' && insufficient) {
      insufficient.hidden = false;
    }
  }

  function loadDigest() {
    ['week', 'month'].forEach(function (period) {
      fetch('/api/digest?period=' + period, { credentials: 'same-origin' })
        .then(function (response) { return response.json(); })
        .then(function (data) { fillDigest(period === 'week' ? 'digest-week' : 'digest-month', data); })
        .catch(function () {});
    });
  }

  function load() {
    setLoading(true);
    var params = { period: state.period };
    if (state.tags.length) params.tags = state.tags;
    fetch('/api/analytics' + qs(params), { credentials: 'same-origin' })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        renderCharts(data);
        var err = document.getElementById('analytics-error');
        if (err) err.hidden = true;
      })
      .catch(function (error) {
        var err = document.getElementById('analytics-error');
        if (err) {
          err.textContent = 'Не удалось загрузить аналитику: ' + error.message;
          err.hidden = false;
        }
      })
      .finally(function () { setLoading(false); });
  }

  function initPeriodSwitch() {
    var buttons = document.querySelectorAll('.period-btn');
    buttons.forEach(function (button) {
      button.addEventListener('click', function () {
        state.period = Number(button.getAttribute('data-period'));
        buttons.forEach(function (other) {
          var active = other === button;
          other.classList.toggle('active', active);
          other.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        load();
      });
    });
  }

  function initTagFilter() {
    var inputs = document.querySelectorAll('#tag-filter input[type="checkbox"]');
    inputs.forEach(function (input) {
      input.addEventListener('change', function () {
        state.tags = Array.prototype.filter
          .call(inputs, function (i) { return i.checked; })
          .map(function (i) { return i.value; });
        load();
      });
    });
  }

  function initResize() {
    var timer = null;
    window.addEventListener('resize', function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(load, 250);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (!document.getElementById('chart-mood')) return;
    initPeriodSwitch();
    initTagFilter();
    initResize();
    load();
    loadDigest();
  });
})();
