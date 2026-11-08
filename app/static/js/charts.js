/* Графики «Баланс» на чистом SVG (без внешних библиотек).
   График 1: линия настроения + столбцы выполненных задач.
   График 2: линия стресса отдельно (шкалы не смешиваются).
   Tooltip: дата, настроение, стресс, число выполненных задач (AC-18).
   Доступность: график фокусируем, стрелки листают дни, Esc закрывает подсказку. */
(function () {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';
  var tooltip = null;

  function el(name, attrs, parent) {
    var node = document.createElementNS(NS, name);
    Object.keys(attrs || {}).forEach(function (key) {
      node.setAttribute(key, attrs[key]);
    });
    if (parent) parent.appendChild(node);
    return node;
  }

  function parseDate(iso) {
    var parts = String(iso).split('-');
    return parts[2] + '.' + parts[1] + '.' + parts[0];
  }

  function longDate(iso) {
    var parts = String(iso).split('-');
    var months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
      'августа', 'сентября', 'октября', 'ноября', 'декабря'];
    return Number(parts[2]) + ' ' + months[Number(parts[1]) - 1] + ' ' + parts[0];
  }

  function getTooltip() {
    if (!tooltip) tooltip = document.getElementById('chart-tooltip');
    return tooltip;
  }

  function showTooltip(day, x, y) {
    var tip = getTooltip();
    if (!tip) return;
    tip.innerHTML =
      '<strong>' + longDate(day.date) + '</strong>' +
      '<div class="tt-row"><span>настроение</span><b>' + (day.mood == null ? '—' : day.mood + '/5') + '</b></div>' +
      '<div class="tt-row"><span>стресс</span><b>' + (day.stress == null ? '—' : day.stress + '/10') + '</b></div>' +
      '<div class="tt-row"><span>выполнено задач</span><b>' + day.completed + '</b></div>';
    tip.hidden = false;
    tip.setAttribute('aria-hidden', 'false');

    var rect = tip.getBoundingClientRect();
    var left = Math.min(x + 14, window.innerWidth - rect.width - 8);
    var top = Math.max(8, y - rect.height - 14);
    tip.style.left = Math.max(8, left) + 'px';
    tip.style.top = top + 'px';
  }

  function hideTooltip() {
    var tip = getTooltip();
    if (!tip) return;
    tip.hidden = true;
    tip.setAttribute('aria-hidden', 'true');
  }

  /* Отрисовка одного графика.
     options: { lineKey, lineMin, lineMax, bars: bool, lineClass, dotClass } */
  function render(container, days, options) {
    container.innerHTML = '';
    if (!days || !days.length) return;

    var width = Math.max(280, container.clientWidth || 600);
    var height = 240;
    var pad = { top: 14, right: 14, bottom: 30, left: 30 };
    var innerW = width - pad.left - pad.right;
    var innerH = height - pad.top - pad.bottom;

    var svg = el('svg', {
      viewBox: '0 0 ' + width + ' ' + height,
      width: width,
      height: height,
      role: 'presentation'
    }, container);

    var n = days.length;
    var stepX = n > 1 ? innerW / (n - 1) : 0;

    function xAt(i) { return pad.left + (n > 1 ? i * stepX : innerW / 2); }

    // ось Y линии (шкала показания)
    var min = options.lineMin;
    var max = options.lineMax;
    function yLine(value) {
      return pad.top + innerH - ((value - min) / (max - min)) * innerH;
    }

    // сетка и подписи Y (5 ровных делений)
    var ticks = [];
    var tickStep = (max - min) / 4;
    for (var t = 0; t <= 4; t++) {
      ticks.push(Math.round(min + tickStep * t));
    }
    ticks.forEach(function (value) {
      var y = yLine(value);
      el('line', { x1: pad.left, y1: y, x2: width - pad.right, y2: y, 'class': 'grid-line' }, svg);
      var label = el('text', { x: pad.left - 6, y: y + 3, 'text-anchor': 'end', 'class': 'axis-text' }, svg);
      label.textContent = value;
    });

    // столбцы выполненных задач (только график 1) — своя шкала 0..max
    if (options.bars) {
      var maxCompleted = days.reduce(function (acc, d) { return Math.max(acc, d.completed || 0); }, 0);
      var barMax = Math.max(1, maxCompleted);
      var barW = Math.max(4, Math.min(22, (stepX || innerW) * 0.55));
      days.forEach(function (day, i) {
        var count = day.completed || 0;
        if (!count) return;
        var h = (count / barMax) * (innerH * 0.85);
        // столбцы не должны перекрывать подписи оси Y
        var left = Math.max(pad.left + 1, xAt(i) - barW / 2);
        var right = Math.min(width - pad.right - 1, xAt(i) + barW / 2);
        el('rect', {
          x: left,
          y: pad.top + innerH - h,
          width: Math.max(2, right - left),
          height: h,
          rx: 3,
          'class': 'bar'
        }, svg);
      });
    }

    // линия с разрывами там, где нет данных
    var path = '';
    var started = false;
    days.forEach(function (day, i) {
      var value = day[options.lineKey];
      if (value == null) { started = false; return; }
      var x = xAt(i);
      var y = yLine(value);
      path += (started ? ' L ' : ' M ') + x + ' ' + y;
      started = true;
    });
    if (path) {
      el('path', { d: path.trim(), 'class': options.lineClass }, svg);
      days.forEach(function (day, i) {
        var value = day[options.lineKey];
        if (value == null) return;
        el('circle', { cx: xAt(i), cy: yLine(value), r: n > 40 ? 2 : 3.5, 'class': options.dotClass }, svg);
      });
    }

    // подписи X: первая, середняя, последняя дата
    var labelIndexes = n <= 2 ? [0, n - 1] : [0, Math.floor((n - 1) / 2), n - 1];
    labelIndexes.forEach(function (i, order) {
      var label = el('text', {
        x: xAt(i),
        y: height - 8,
        'text-anchor': order === 0 ? 'start' : (order === 2 ? 'end' : 'middle'),
        'class': 'axis-text'
      }, svg);
      label.textContent = parseDate(days[i].date);
    });

    // зона наведения + вертикальная линия
    var hoverLine = el('line', {
      x1: 0, y1: pad.top, x2: 0, y2: pad.top + innerH,
      'class': 'hover-line', visibility: 'hidden'
    }, svg);

    var hoverDot = el('circle', { r: 5, 'class': options.dotClass, visibility: 'hidden' }, svg);

    function activate(index, clientX, clientY) {
      if (index < 0 || index >= n) return;
      var day = days[index];
      var x = xAt(index);
      hoverLine.setAttribute('x1', x);
      hoverLine.setAttribute('x2', x);
      hoverLine.setAttribute('visibility', 'visible');
      var value = day[options.lineKey];
      if (value == null) {
        hoverDot.setAttribute('visibility', 'hidden');
      } else {
        hoverDot.setAttribute('cx', x);
        hoverDot.setAttribute('cy', yLine(value));
        hoverDot.setAttribute('visibility', 'visible');
      }
      var rect = container.getBoundingClientRect();
      var px = clientX == null ? rect.left + (x / width) * rect.width : clientX;
      var py = clientY == null ? rect.top + rect.height / 2 : clientY;
      showTooltip(day, px, py);
      container._activeIndex = index;
    }

    function deactivate() {
      hoverLine.setAttribute('visibility', 'hidden');
      hoverDot.setAttribute('visibility', 'hidden');
      hideTooltip();
    }

    function indexFromEvent(event) {
      var rect = svg.getBoundingClientRect();
      var localX = ((event.clientX - rect.left) / rect.width) * width;
      if (n === 1) return 0;
      var idx = Math.round((localX - pad.left) / stepX);
      return Math.max(0, Math.min(n - 1, idx));
    }

    svg.addEventListener('mousemove', function (event) {
      activate(indexFromEvent(event), event.clientX, event.clientY);
    });
    svg.addEventListener('mouseleave', deactivate);

    // клавиатурная навигация (доступность)
    container.addEventListener('keydown', function (event) {
      var active = container._activeIndex;
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
        event.preventDefault();
        if (active == null) active = n - 1;
        else active += (event.key === 'ArrowRight' ? 1 : -1);
        active = Math.max(0, Math.min(n - 1, active));
        activate(active);
      } else if (event.key === 'Home') {
        event.preventDefault(); activate(0);
      } else if (event.key === 'End') {
        event.preventDefault(); activate(n - 1);
      } else if (event.key === 'Escape') {
        deactivate();
      }
    });
    container.addEventListener('blur', deactivate);
  }

  window.BalansCharts = {
    renderMood: function (container, days) {
      render(container, days, {
        lineKey: 'mood', lineMin: 1, lineMax: 5, bars: true,
        lineClass: 'line-mood', dotClass: 'dot-mood'
      });
    },
    renderStress: function (container, days) {
      render(container, days, {
        lineKey: 'stress', lineMin: 1, lineMax: 10, bars: false,
        lineClass: 'line-stress', dotClass: 'dot-stress'
      });
    }
  };
})();
