(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem('tw_' + k)) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem('tw_' + k, JSON.stringify(v)); } catch {} }
  };

  // --- Тост ---
  const toast = document.getElementById('toast');
  let tt;
  const notify = (text) => {
    toast.textContent = text; toast.classList.add('show');
    clearTimeout(tt); tt = setTimeout(() => toast.classList.remove('show'), 2600);
  };

  // --- Достижения ---
  const ACH = {
    visit:  { ico: '🌙', name: 'Первый вход', text: 'Вы открыли TWILIGHT.' },
    calc:   { ico: '🧮', name: 'Экономист', text: 'Посчитали стоимость в калькуляторе.' },
    seat:   { ico: '🪑', name: 'Своё место', text: 'Выбрали место в карте зала.' },
    fav:    { ico: '♥', name: 'Коллекционер', text: 'Добавили игру в избранное.' },
    mode:   { ico: '◐', name: 'Перемена света', text: 'Сменили визуальный режим.' },
    member: { ico: '✦', name: 'Участник', text: 'Создали цифровую карту.' }
  };
  let unlocked = store.get('ach', {});
  const achGrid = document.getElementById('achGrid');
  const renderAch = () => {
    achGrid.innerHTML = Object.entries(ACH).map(([k, a]) => `
      <div class="card ach-card ${unlocked[k] ? 'unlocked' : 'locked'}">
        <div class="ach-ico">${a.ico}</div>
        <div><h3>${a.name}</h3><p>${unlocked[k] ? a.text : 'Откройте, чтобы увидеть.'}</p></div>
      </div>`).join('');
  };
  const unlock = (k) => {
    if (unlocked[k]) return;
    unlocked[k] = true; store.set('ach', unlocked); renderAch();
    notify('Достижение: ' + ACH[k].name);
  };
  renderAch();
  unlock('visit');
  window.TW = { unlock, notify };  // нужно club.js

  // --- Живые часы и тариф сейчас ---
  const clock = document.getElementById('clock');
  const tariffNow = document.getElementById('tariffNow');
  const tick = () => {
    const d = new Date();
    clock.textContent = d.toLocaleTimeString('ru-RU');
    const h = d.getHours();
    const night = h >= 23 || h < 8;
    tariffNow.textContent = night ? '· сейчас ночной тариф' : '· сейчас обычное время';
  };
  tick(); setInterval(tick, 1000);

  // --- Калькулятор: отметка достижения ---
  document.getElementById('calcTariff').addEventListener('change', () => unlock('calc'));

  // --- Избранные игры ---
  const favs = new Set(store.get('favs', []));
  const favCount = document.getElementById('favCount');
  const favList = document.getElementById('favList');
  const names = {};
  document.querySelectorAll('.game-card').forEach((c) => { names[c.dataset.id] = c.querySelector('h3').textContent; });
  const renderFavs = () => {
    favCount.textContent = favs.size;
    favList.textContent = favs.size ? [...favs].map((id) => names[id]).join(' · ') : 'пока пусто';
    document.querySelectorAll('.game-card').forEach((c) => {
      const b = c.querySelector('.fav');
      const on = favs.has(c.dataset.id);
      b.classList.toggle('on', on); b.textContent = on ? '♥' : '♡';
    });
  };
  document.querySelectorAll('.fav').forEach((b) => {
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = b.closest('.game-card').dataset.id;
      favs.has(id) ? favs.delete(id) : favs.add(id);
      store.set('favs', [...favs]); renderFavs();
      if (favs.size) unlock('fav');
    });
  });
  renderFavs();

  // --- Визуальные режимы ---
  const MODES = ['mode-midnight', 'mode-eclipse', 'mode-blood'];
  const modeBtn = document.getElementById('modeBtn');
  let mi = MODES.indexOf(store.get('mode', 'mode-midnight'));
  if (mi < 0) mi = 0;
  const applyMode = () => {
    document.body.classList.remove(...MODES);
    document.body.classList.add(MODES[mi]);
    modeBtn.title = 'Режим: ' + ['Midnight', 'Eclipse', 'Blood Moon'][mi];
  };
  applyMode();
  modeBtn.addEventListener('click', () => {
    mi = (mi + 1) % MODES.length;
    store.set('mode', MODES[mi]); applyMode();
    notify('Режим: ' + ['Midnight', 'Eclipse', 'Blood Moon'][mi]);
    unlock('mode');
  });

  // --- Фоновая музыка (синтез, по умолчанию выключена) ---
  const musicBtn = document.getElementById('musicBtn');
  let ctx = null, nodes = null;
  const startMusic = () => {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    const gain = ctx.createGain(); gain.gain.value = 0;
    const filter = ctx.createBiquadFilter(); filter.type = 'lowpass'; filter.frequency.value = 500;
    const o1 = ctx.createOscillator(); o1.type = 'sine'; o1.frequency.value = 55;
    const o2 = ctx.createOscillator(); o2.type = 'triangle'; o2.frequency.value = 82.4;
    o1.connect(filter); o2.connect(filter); filter.connect(gain); gain.connect(ctx.destination);
    o1.start(); o2.start();
    gain.gain.linearRampToValueAtTime(0.05, ctx.currentTime + 2);
    nodes = { o1, o2, gain };
  };
  const stopMusic = () => {
    if (!nodes) return;
    nodes.gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.5);
    const { o1, o2 } = nodes;
    setTimeout(() => { o1.stop(); o2.stop(); }, 600);
    nodes = null;
  };
  let musicOn = store.get('music', false);
  const setMusic = (on) => {
    musicOn = on; store.set('music', on);
    musicBtn.setAttribute('aria-pressed', String(on));
    on ? startMusic() : stopMusic();
  };
  musicBtn.addEventListener('click', () => { setMusic(!musicOn); notify(musicOn ? 'Музыка включена' : 'Музыка выключена'); });
  // Браузер не даст играть звук без нажатия, поэтому выключено по умолчанию
  musicBtn.setAttribute('aria-pressed', 'false');
  if (reduce) musicBtn.style.display = 'none';

  // --- Первое посещение карты участника и т.п. ---
  window.addEventListener('scroll', () => {
    if (scrollY > document.body.scrollHeight * 0.6) unlock('visit');
  }, { passive: true });
})();
