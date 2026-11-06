// Данные клуба на главной: калькулятор, карта зала, бронирование (всё берётся с сервера).
(() => {
  const $ = (id) => document.getElementById(id);
  const tw = () => window.TW || { unlock() {}, notify() {} };
  const fmt = (n) => Number(n).toLocaleString('ru-RU') + '\u00a0₽';
  const csrf = () => (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
  const dataEl = $('tariffsData');
  const tariffs = dataEl ? JSON.parse(dataEl.textContent) : [];

  // --- Калькулятор: цена приходит с сервера ---
  const cat = $('calcCat'), tariff = $('calcTariff'), hrs = $('calcHours'), out = $('calcHoursOut'), total = $('calcTotal');
  if (cat && tariff && hrs) {
    const fillTariffs = () => {
      tariff.innerHTML = '';
      tariffs.filter((t) => t.category === cat.value).forEach((t) => {
        const o = document.createElement('option');
        o.value = t.id; o.textContent = t.name; tariff.appendChild(o);
      });
    };
    let timer;
    const calc = () => {
      out.textContent = hrs.value;
      if (!tariff.value) { total.textContent = '—'; return; }
      clearTimeout(timer);
      timer = setTimeout(async () => {
        try {
          const r = await fetch(`/api/quote/?tariff_id=${tariff.value}&hours=${hrs.value}`);
          const d = await r.json();
          total.textContent = r.ok ? fmt(d.total) : 'ошибка';
          total.classList.remove('bump'); void total.offsetWidth; total.classList.add('bump');
        } catch { total.textContent = 'нет связи'; }
      }, 120);
    };
    cat.addEventListener('input', () => { fillTariffs(); calc(); });
    tariff.addEventListener('change', () => { tw().unlock('calc'); calc(); });
    hrs.addEventListener('input', calc);
    fillTariffs(); calc();
  }

  // --- Карта зала ---
  const grid = $('seatGrid'), info = $('seatInfo');
  const seats = grid ? [...grid.querySelectorAll('.seat')] : [];
  const bkComputer = $('bkComputer');
  seats.forEach((s) => {
    s.addEventListener('click', () => {
      info.textContent = '';
      const d = s.dataset;
      if (s.classList.contains('busy')) {
        info.textContent = `Место ${d.num} занято: ${d.reason || 'сейчас недоступно'}`;
        return;
      }
      seats.forEach((x) => x.classList.remove('selected'));
      s.classList.add('selected');
      info.textContent = `Место ${d.num} · ${d.label}` + (d.rate ? ` · ${fmt(d.rate)}/ч` : '');
      if (d.specs) { const sp = document.createElement('div'); sp.className = 'seat-spec'; sp.textContent = d.specs; info.appendChild(sp); }
      if (bkComputer) bkComputer.value = d.id;
      tw().unlock('seat');
    });
  });
  document.querySelectorAll('#hallFilters .chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('#hallFilters .chip').forEach((c) => c.classList.toggle('active', c === chip));
      const f = chip.dataset.f;
      seats.forEach((s) => s.classList.toggle('dim', f !== 'all' && s.dataset.cat !== f));
    });
  });

  // --- Бронирование ---
  const form = $('bookingForm');
  if (!form) return;
  const bkCat = $('bkCat'), bkDate = $('bkDate'), bkTime = $('bkTime'), hours = $('hours'), hoursOut = $('hoursOut');
  const note = $('formNote'), btn = $('submitBtn');
  const pad = (n) => String(n).padStart(2, '0');
  const stamp = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:00`;

  const filterOptions = () => {
    [...bkComputer.options].forEach((o) => {
      if (!o.value) return;
      o.hidden = !!bkCat.value && o.dataset.cat !== bkCat.value;
    });
    if (bkComputer.selectedOptions[0] && bkComputer.selectedOptions[0].hidden) bkComputer.value = '';
  };
  const refreshAvailability = async () => {
    if (!bkDate.value || !bkTime.value) return;
    const start = new Date(`${bkDate.value}T${bkTime.value}`);
    if (isNaN(start)) return;
    const end = new Date(start.getTime() + Number(hours.value) * 3600e3);
    try {
      const r = await fetch(`${form.dataset.computers}?start=${stamp(start)}&end=${stamp(end)}`);
      if (!r.ok) return;
      const { computers } = await r.json();
      const byId = Object.fromEntries(computers.map((c) => [String(c.id), c]));
      [...bkComputer.options].forEach((o) => {
        const c = byId[o.value];
        if (!c) return;
        o.dataset.label = o.dataset.label || o.textContent;
        o.disabled = !c.available;
        o.textContent = o.dataset.label + (c.available ? '' : ' (занято)');
      });
      if (bkComputer.selectedOptions[0] && bkComputer.selectedOptions[0].disabled) bkComputer.value = '';
    } catch { /* без связи просто не обновляем */ }
  };
  bkCat.addEventListener('input', filterOptions);
  [bkDate, bkTime].forEach((el) => el.addEventListener('change', refreshAvailability));
  hours.addEventListener('input', () => { hoursOut.textContent = hours.value; });
  hours.addEventListener('change', refreshAvailability);
  refreshAvailability();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    note.textContent = '';
    if (!bkComputer.value) { note.textContent = 'Выберите компьютер.'; return; }
    btn.classList.add('is-loading'); btn.textContent = 'Отправляем…';
    try {
      const r = await fetch(form.dataset.api, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
        body: JSON.stringify({ computer_id: bkComputer.value, date: bkDate.value, time: bkTime.value, hours: hours.value })
      });
      const d = await r.json();
      note.textContent = d.ok ? d.message : (d.error || 'Не удалось создать бронь.');
      if (d.ok) { tw().notify('Заявка отправлена'); refreshAvailability(); }
    } catch { note.textContent = 'Нет связи с сервером. Попробуйте ещё раз.'; }
    btn.classList.remove('is-loading'); btn.textContent = 'Отправить заявку';
  });
})();
