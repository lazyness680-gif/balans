/* «Баланс»: тема, подтверждения удаления, вспомогательные UI-действия.
   Тема: выбор хранится в профиле и localStorage (раздел 8 ТЗ). */
(function () {
  'use strict';

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('balans-theme', theme); } catch (e) {}
  }

  function initThemeToggle() {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
      var next = current === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      // сохраняем выбор в профиле (FR-39: выбор сохраняется)
      fetch('/api/me', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: next })
      }).catch(function () {});
    });
  }

  // Подтверждение удаления (FR-12, FR-16): карточки с data-confirm
  function initConfirmForms() {
    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
      form.addEventListener('submit', function (event) {
        if (!window.confirm(form.getAttribute('data-confirm'))) {
          event.preventDefault();
        }
      });
    });
  }

  // Плавное скрытие служебных сообщений
  function initAutoAlerts() {
    document.querySelectorAll('.alert-ok').forEach(function (el) {
      window.setTimeout(function () {
        el.style.transition = 'opacity .4s';
        el.style.opacity = '0';
        window.setTimeout(function () { el.remove(); }, 450);
      }, 4000);
    });
  }

  // Отмеченный чип тега/темы визуально подсвечиваем (для :has как fallback)
  function initChipFallback() {
    if (CSS && CSS.supports && CSS.supports('selector(:has(*))')) return;
    document.querySelectorAll('.chip input, .scale-chip input').forEach(function (input) {
      input.addEventListener('change', function () {
        var group = input.name;
        if (input.type === 'radio' && group) {
          document.querySelectorAll('input[name="' + group + '"]').forEach(function (other) {
            var label = other.closest('.chip, .scale-chip');
            if (label) label.classList.toggle('selected', other.checked);
          });
        } else {
          var label = input.closest('.chip, .scale-chip');
          if (label) label.classList.toggle('selected', input.checked);
        }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initThemeToggle();
    initConfirmForms();
    initAutoAlerts();
    initChipFallback();
  });
})();
