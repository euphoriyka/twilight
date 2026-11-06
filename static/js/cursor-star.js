// Курсор-звезда TWILIGHT: маленькая шестиконечная звезда плавно следует за указателем.
// Не мешает кликам (pointer-events: none), выключена на сенсорных экранах.
(() => {
  const canHover = matchMedia('(hover: hover) and (pointer: fine)').matches;
  if (!canHover) return;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const noTrail = reduce || document.body.classList.contains('staff');  // в админке без шлейфа

  const star = document.createElement('div');
  star.className = 'cursor-star';
  star.setAttribute('aria-hidden', 'true');
  star.innerHTML = '<img src="/static/img/edward.png" alt="" draggable="false">';
  document.body.appendChild(star);

  let tx = -100, ty = -100, x = -100, y = -100, rot = 0, over = false, running = false, lastTrail = 0;
  const ease = reduce ? 1 : 0.22;
  const TRAIL_MAX = 14;
  const trail = [];
  if (!noTrail) {
    for (let i = 0; i < TRAIL_MAX; i++) {
      const d = document.createElement('i');
      d.className = 'cursor-dot';
      d.setAttribute('aria-hidden', 'true');
      document.body.appendChild(d);
      trail.push(d);
    }
  }
  let ti = 0;
  const spawn = (px, py) => {
    const d = trail[ti++ % TRAIL_MAX];
    d.style.left = px + 'px'; d.style.top = py + 'px';
    d.classList.remove('go'); void d.offsetWidth; d.classList.add('go');
  };

  const loop = () => {
    const dx = tx - x, dy = ty - y;
    x += dx * ease; y += dy * ease;
    if (!reduce) rot += (Math.max(-40, Math.min(40, dx)) * 0.6 - rot) * 0.15;
    star.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%) rotate(${rot}deg) scale(${over ? 1.5 : 1})`;
    if (Math.abs(dx) + Math.abs(dy) > 0.3 || Math.abs(rot) > 0.3) requestAnimationFrame(loop);
    else running = false;  // не крутим цикл впустую, пока курсор стоит
  };
  const kick = () => { if (!running) { running = true; requestAnimationFrame(loop); } };

  window.addEventListener('pointermove', (e) => {
    tx = e.clientX; ty = e.clientY;
    star.classList.add('on');
    if (!noTrail && e.timeStamp - lastTrail > 45) { lastTrail = e.timeStamp; spawn(tx, ty); }
    kick();
  }, { passive: true });
  document.addEventListener('pointerleave', () => star.classList.remove('on'));
  document.addEventListener('pointerover', (e) => {
    over = !!e.target.closest('a, button, select, input, label, summary, [role="button"], .seat, .game-card');
    kick();
  });
  window.addEventListener('pointerdown', () => star.classList.add('press'));
  window.addEventListener('pointerup', () => star.classList.remove('press'));
})();
