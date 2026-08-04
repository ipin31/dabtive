document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-copy]');
  if (!button) return;
  const target = document.querySelector(button.dataset.copy);
  if (!target) return;
  try {
    await navigator.clipboard.writeText(target.textContent.trim());
    const old = button.textContent;
    button.textContent = 'COPIED';
    setTimeout(() => button.textContent = old, 1400);
  } catch (_) {
    window.getSelection().selectAllChildren(target);
  }
});


const leadSearch = document.querySelector('[data-lead-search]');
if (leadSearch) {
  const rows = [...document.querySelectorAll('[data-lead-rows] tr[data-search]')];
  const empty = document.querySelector('[data-no-lead-result]');
  const filterLeads = () => {
    const query = leadSearch.value.trim().toLowerCase();
    let visible = 0;
    rows.forEach((row) => {
      const matches = !query || row.dataset.search.toLowerCase().includes(query);
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    if (empty) empty.hidden = visible !== 0;
  };
  leadSearch.addEventListener('input', filterLeads);
}

const paidToggle = document.querySelector('[data-paid-toggle]');
const paidFields = document.querySelector('[data-paid-fields]');
if (paidToggle && paidFields) {
  const syncPaidFields = () => paidFields.classList.toggle('is-hidden', !paidToggle.checked);
  paidToggle.addEventListener('change', syncPaidFields);
  syncPaidFields();
}

// Product screenshot carousel. Works with buttons, dots, keyboard and touch swipe.
document.querySelectorAll('[data-carousel]').forEach((carousel) => {
  const slides = [...carousel.querySelectorAll('[data-slide]')];
  const dots = [...carousel.querySelectorAll('[data-carousel-dot]')];
  const previous = carousel.querySelector('[data-carousel-prev]');
  const next = carousel.querySelector('[data-carousel-next]');
  if (slides.length < 2) return;

  let active = Math.max(0, slides.findIndex((slide) => slide.classList.contains('is-active')));
  const show = (index) => {
    active = (index + slides.length) % slides.length;
    slides.forEach((slide, slideIndex) => slide.classList.toggle('is-active', slideIndex === active));
    dots.forEach((dot, dotIndex) => {
      dot.classList.toggle('is-active', dotIndex === active);
      dot.setAttribute('aria-selected', dotIndex === active ? 'true' : 'false');
    });
  };

  previous?.addEventListener('click', () => show(active - 1));
  next?.addEventListener('click', () => show(active + 1));
  dots.forEach((dot) => dot.addEventListener('click', () => show(Number(dot.dataset.carouselDot))));
  carousel.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowLeft') show(active - 1);
    if (event.key === 'ArrowRight') show(active + 1);
  });

  let touchStart = null;
  carousel.addEventListener('touchstart', (event) => {
    touchStart = event.changedTouches[0]?.clientX ?? null;
  }, { passive: true });
  carousel.addEventListener('touchend', (event) => {
    if (touchStart === null) return;
    const distance = (event.changedTouches[0]?.clientX ?? touchStart) - touchStart;
    if (Math.abs(distance) > 45) show(active + (distance < 0 ? 1 : -1));
    touchStart = null;
  }, { passive: true });
});

// Prevent accidental duplicate lead submissions while encryption job is queued.
document.querySelectorAll('[data-request-form]').forEach((form) => {
  form.addEventListener('submit', () => {
    const button = form.querySelector('button[type="submit"]');
    if (!button || button.disabled) return;
    button.disabled = true;
    const label = button.querySelector('span');
    if (label) label.textContent = 'Memproses...';
  });
});
