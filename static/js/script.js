(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fine = matchMedia('(pointer: fine)').matches;
  const isMobile = innerWidth < 720 || !fine;
  const hasGsap = typeof gsap !== 'undefined';
  const hasST = typeof ScrollTrigger !== 'undefined';
  const loader = document.getElementById('loader');

  // --- Разбиваем заголовок на буквы для анимации ---
  const h1 = document.getElementById('heroTitle');
  const word = h1.textContent;
  h1.innerHTML = [...word].map((c) => `<span class="wrap"><span class="ch">${c}</span></span>`).join('');

  // --- Загрузка и вход в первый экран ---
  const finishLoader = () => loader.classList.add('done');
  if (reduce || !hasGsap) {
    finishLoader();
    document.querySelectorAll('.reveal').forEach((el) => el.classList.add('js-fallback', 'visible'));
  } else {
    const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });
    tl.to(loader, { yPercent: -100, duration: 1, ease: 'power3.inOut', delay: 0.3, onComplete: finishLoader })
      .from('.hero .ch', { yPercent: 110, opacity: 0, duration: 1.1, stagger: 0.07, ease: 'expo.out' }, '-=0.5')
      .from('.eyebrow, .slogan, .hero-text', { y: 20, opacity: 0, duration: 0.8, stagger: 0.12 }, '-=0.6')
      .from('.star-svg', { scale: 0, rotate: -90, opacity: 0, duration: 1.2, ease: 'back.out(1.4)' }, '-=0.9')
      .from('.hero-actions .btn', { y: 20, opacity: 0, duration: 0.6, stagger: 0.1 }, '-=0.6');
  }

  // --- Появление секций при прокрутке (GSAP ScrollTrigger) ---
  if (!reduce && hasGsap && hasST) {
    gsap.registerPlugin(ScrollTrigger);
    gsap.utils.toArray('.reveal').forEach((el) => {
      gsap.fromTo(el, { y: 50, opacity: 0 }, {
        y: 0, opacity: 1, duration: 1, ease: 'power3.out',
        scrollTrigger: { trigger: el, start: 'top 88%', once: true }
      });
    });
    // Параллакс декоративных элементов
    gsap.utils.toArray('.parallax').forEach((el) => {
      const speed = Number(el.dataset.speed || 0.2);
      gsap.to(el, {
        yPercent: -30 * speed * 4,
        ease: 'none',
        scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub: true }
      });
    });
  } else if (!hasGsap) {
    // Запасной вариант без GSAP
    const obs = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('visible'); obs.unobserve(e.target); } });
    }, { threshold: 0.15 });
    document.querySelectorAll('.reveal').forEach((el) => { el.classList.add('js-fallback'); obs.observe(el); });
  }

  // --- Параллакс текста на hero при движении мыши ---
  const heroContent = document.querySelector('.hero-content');
  const glow = document.querySelector('.cursor-glow');
  let mx = 0, my = 0, cx = 0, cy = 0;
  if (fine && !reduce) {
    window.addEventListener('pointermove', (e) => {
      mx = e.clientX / innerWidth - 0.5;
      my = e.clientY / innerHeight - 0.5;
      glow.style.transform = `translate(${e.clientX - 210}px, ${e.clientY - 210}px)`;
    });
    const depthLoop = () => {
      cx += (mx - cx) * 0.06; cy += (my - cy) * 0.06;
      const d = Number(heroContent.dataset.depth || 0.5);
      heroContent.style.transform = `translate3d(${cx * -20 * d}px, ${cy * -14 * d}px, 0)`;
      requestAnimationFrame(depthLoop);
    };
    depthLoop();
  } else {
    glow.style.display = 'none';
  }

  // --- Шапка меняется при прокрутке ---
  const topbar = document.querySelector('.topbar');
  window.addEventListener('scroll', () => topbar.classList.toggle('scrolled', scrollY > 40), { passive: true });

  // --- 3D-сцена: туманный лес, луна, частицы (Three.js) ---
  const sceneEl = document.getElementById('scene');
  if (!reduce && typeof THREE !== 'undefined' && sceneEl) {
    const start = () => {
      const w = sceneEl.clientWidth, h = sceneEl.clientHeight;
      const renderer = new THREE.WebGLRenderer({ antialias: !isMobile, alpha: true });
      renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
      renderer.setSize(w, h);
      sceneEl.appendChild(renderer.domElement);

      const scene = new THREE.Scene();
      scene.fog = new THREE.FogExp2(0x080d19, 0.055);
      const camera = new THREE.PerspectiveCamera(55, w / h, 0.1, 200);
      camera.position.set(0, 1.2, 12);

      scene.add(new THREE.AmbientLight(0x243b5a, 0.9));
      const moonLight = new THREE.DirectionalLight(0xaec6e6, 1.1);
      moonLight.position.set(-6, 10, -4);
      scene.add(moonLight);
      const burg = new THREE.PointLight(0x701f3a, 2.2, 30);
      burg.position.set(6, 2, -6);
      scene.add(burg);

      const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(200, 200),
        new THREE.MeshStandardMaterial({ color: 0x080d19, roughness: 1 })
      );
      ground.rotation.x = -Math.PI / 2;
      ground.position.y = -1.5;
      scene.add(ground);

      // Лес: один InstancedMesh вместо сотен отдельных объектов
      const count = isMobile ? 60 : 140;
      const treeGeo = new THREE.ConeGeometry(1, 4, 6);
      treeGeo.translate(0, 2, 0);
      const trees = new THREE.InstancedMesh(treeGeo,
        new THREE.MeshStandardMaterial({ color: 0x17243a, roughness: 0.9, flatShading: true }), count);
      const m = new THREE.Matrix4(), p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3();
      for (let i = 0; i < count; i++) {
        const side = Math.random() < 0.5 ? -1 : 1;
        const x = side * (3 + Math.random() * 26);
        const z = -4 - Math.random() * 66;
        const sc = 0.6 + Math.random() * 1.3;
        p.set(x, -1.5, z);
        s.set(sc, sc * (0.8 + Math.random() * 0.6), sc);
        m.compose(p, q, s);
        trees.setMatrixAt(i, m);
      }
      trees.instanceMatrix.needsUpdate = true;
      scene.add(trees);

      const moon = new THREE.Mesh(new THREE.SphereGeometry(2.2, 32, 32),
        new THREE.MeshBasicMaterial({ color: 0xd9e0ea }));
      moon.position.set(-8, 7, -45);
      scene.add(moon);

      // Частицы тумана и светлячков
      const pn = isMobile ? 150 : 350;
      const pos = new Float32Array(pn * 3);
      for (let i = 0; i < pn; i++) {
        pos[i * 3] = (Math.random() - 0.5) * 40;
        pos[i * 3 + 1] = -2 + Math.random() * 10;
        pos[i * 3 + 2] = -30 + Math.random() * 35;
      }
      const pg = new THREE.BufferGeometry();
      pg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      const points = new THREE.Points(pg, new THREE.PointsMaterial({
        color: 0xd9e0ea, size: 0.06, transparent: true, opacity: 0.55, depthWrite: false
      }));
      scene.add(points);

      // Мышь влияет на камеру только на ПК
      let mx = 0, my = 0, tx = 0, ty = 0;
      if (fine && !isMobile) {
        window.addEventListener('pointermove', (e) => {
          mx = e.clientX / innerWidth - 0.5;
          my = e.clientY / innerHeight - 0.5;
        });
      }

      window.addEventListener('resize', () => {
        const nw = sceneEl.clientWidth, nh = sceneEl.clientHeight;
        renderer.setSize(nw, nh);
        camera.aspect = nw / nh;
        camera.updateProjectionMatrix();
      });

      // Не тратим ресурсы, когда hero не на экране
      let visible = true;
      new IntersectionObserver((en) => { visible = en[0].isIntersecting; }).observe(sceneEl);

      const clock = new THREE.Clock();
      const frame = () => {
        requestAnimationFrame(frame);
        if (!visible) return;
        const t = clock.getElapsedTime();
        tx += (mx - tx) * 0.04;
        ty += (my - ty) * 0.04;
        camera.position.x = tx * 2.5;
        camera.position.y = 1.2 - ty * 1.2;
        camera.lookAt(0, 0.5, -20);
        points.rotation.y = t * 0.02;
        points.position.y = Math.sin(t * 0.3) * 0.2;
        moon.position.y = 7 + Math.sin(t * 0.2) * 0.15;
        burg.intensity = 2.2 + Math.sin(t * 0.8) * 0.2;
        renderer.render(scene, camera);
      };
      frame();
    };
    // Сцену запускаем после загрузки, чтобы не замедлять первый экран
    if ('requestIdleCallback' in window) requestIdleCallback(start, { timeout: 800 });
    else setTimeout(start, 200);
  }

  // --- Наклон карточек за курсором (только ПК) ---
  if (fine && !reduce) {
    document.querySelectorAll('.tilt').forEach((card) => {
      card.addEventListener('pointermove', (e) => {
        const r = card.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;
        const y = (e.clientY - r.top) / r.height - 0.5;
        card.style.transform = `perspective(800px) rotateX(${-y * 8}deg) rotateY(${x * 8}deg) translateY(-4px)`;
      });
      card.addEventListener('pointerleave', () => { card.style.transform = ''; });
    });
    // Магнитные кнопки
    document.querySelectorAll('.magnetic').forEach((btn) => {
      btn.addEventListener('pointermove', (e) => {
        const r = btn.getBoundingClientRect();
        btn.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * 0.15}px, ${(e.clientY - r.top - r.height / 2) * 0.25}px)`;
      });
      btn.addEventListener('pointerleave', () => { btn.style.transform = ''; });
    });
  }

  // --- Карусель игр: стрелки и перетаскивание ---
  const carousel = document.getElementById('carousel');
  const step = () => carousel.querySelector('.game-card').offsetWidth + 20;
  document.querySelectorAll('.arrow').forEach((b) => {
    b.addEventListener('click', () => carousel.scrollBy({ left: step() * Number(b.dataset.dir), behavior: 'smooth' }));
  });
  let down = false, startX = 0, startScroll = 0, moved = false;
  carousel.addEventListener('pointerdown', (e) => { down = true; moved = false; startX = e.clientX; startScroll = carousel.scrollLeft; });
  window.addEventListener('pointerup', () => { if (down) { down = false; carousel.classList.remove('dragging'); } });
  carousel.addEventListener('pointermove', (e) => {
    if (!down) return;
    const dx = e.clientX - startX;
    if (Math.abs(dx) > 5) { moved = true; carousel.classList.add('dragging'); }
    carousel.scrollLeft = startScroll - dx;
  });
  carousel.addEventListener('click', (e) => { if (moved) e.preventDefault(); }, true);
})();
