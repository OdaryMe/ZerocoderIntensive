/* =========================================================================
   Signal — AI Job Digest
   radar.js: анимация «AI-радара» на первом экране.

   Радар рисуется на canvas: кольца, развёртка и метки направлений поиска.
   Когда луч проходит мимо метки — она на мгновение загорается.
   ========================================================================= */

(function () {
  "use strict";

  const canvas = document.getElementById("radarCanvas");
  if (!canvas || !canvas.getContext) return;

  const ctx = canvas.getContext("2d");
  const directions = (window.SIGNAL_DATA && window.SIGNAL_DATA.directions) || [];
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const TAU = Math.PI * 2;
  const FULL_TURN_MS = 14000; // полный оборот луча — 14 секунд

  let pixelRatio = 1;
  let width = 0;
  let height = 0;
  let sweepAngle = -Math.PI / 2;
  let animationId = null;
  let lastFrame = null;

  /* Геометрия меток: направления распределены по кругу,
     радиус каждого подбирается детерминированно (без случайностей). */
  const blips = directions.map((direction, index) => {
    const fraction = ((index * 2654435761) % 1000) / 1000;
    return {
      direction: direction,
      angle: (index / Math.max(directions.length, 1)) * TAU - Math.PI / 2,
      radiusFactor: 0.34 + 0.56 * fraction
    };
  });

  function resize() {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(rect.width * pixelRatio);
    canvas.height = Math.round(rect.height * pixelRatio);
    width = rect.width;
    height = rect.height;
    ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    if (reducedMotion) draw();
  }

  function circle(x, y, radius) {
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, TAU);
    ctx.stroke();
  }

  function drawSweep(cx, cy, radius) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(sweepAngle);

    // Шлейф луча — сектор с градиентной прозрачностью
    const gradient = ctx.createRadialGradient(0, 0, 0, 0, 0, radius);
    gradient.addColorStop(0, "rgba(34, 211, 238, 0.20)");
    gradient.addColorStop(0.75, "rgba(34, 211, 238, 0.06)");
    gradient.addColorStop(1, "rgba(34, 211, 238, 0)");
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.arc(0, 0, radius, -0.85, 0);
    ctx.closePath();
    ctx.fill();

    // Сам луч
    ctx.strokeStyle = "rgba(163, 230, 53, 0.85)";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(radius, 0);
    ctx.stroke();

    ctx.restore();
  }

  function drawBlip(blip, cx, cy, radius, now) {
    const x = cx + Math.cos(blip.angle) * radius * blip.radiusFactor;
    const y = cy + Math.sin(blip.angle) * radius * blip.radiusFactor;

    // Яркость: метка вспыхивает, когда луч только что её прошёл
    let delta = sweepAngle - blip.angle;
    delta = ((delta % TAU) + TAU) % TAU;
    const glow = Math.max(0, 1 - delta / (TAU * 0.5));
    const pulse = 0.5 + 0.5 * Math.sin(now / 600 + blip.angle * 3);
    const alpha = 0.28 + 0.72 * glow;

    // Точка направления
    ctx.beginPath();
    ctx.arc(x, y, 3.4 + glow * 2.4, 0, TAU);
    ctx.fillStyle = hexToRgba(blip.direction.color, alpha);
    ctx.fill();

    // Кольцо вокруг свежей метки
    if (glow > 0.25) {
      ctx.beginPath();
      ctx.arc(x, y, 7 + glow * 9, 0, TAU);
      ctx.strokeStyle = hexToRgba(blip.direction.color, glow * 0.5 * pulse);
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Подпись направления
    const label = blip.direction.short || blip.direction.label;
    ctx.font = '10px "JetBrains Mono", Consolas, monospace';
    ctx.fillStyle = hexToRgba(blip.direction.color, 0.35 + glow * 0.6);
    ctx.textBaseline = "middle";
    const onRight = x >= cx;
    ctx.textAlign = onRight ? "left" : "right";
    ctx.fillText(label, x + (onRight ? 10 : -10), y);
  }

  function draw() {
    if (!width || !height) return;
    ctx.clearRect(0, 0, width, height);

    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(width, height) / 2 - 30;

    // Кольца
    ctx.lineWidth = 1;
    [1, 0.74, 0.48, 0.24].forEach((factor, index) => {
      ctx.strokeStyle = index === 0
        ? "rgba(34, 211, 238, 0.28)"
        : "rgba(255, 255, 255, " + (0.10 - index * 0.018) + ")";
      circle(cx, cy, radius * factor);
    });

    // Внешний пунктир
    ctx.setLineDash([3, 8]);
    ctx.strokeStyle = "rgba(139, 92, 246, 0.4)";
    circle(cx, cy, radius + 9);
    ctx.setLineDash([]);

    // Оси и подписи градусов
    ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
    ctx.beginPath();
    ctx.moveTo(cx - radius, cy);
    ctx.lineTo(cx + radius, cy);
    ctx.moveTo(cx, cy - radius);
    ctx.lineTo(cx, cy + radius);
    ctx.stroke();

    ctx.font = '9px "JetBrains Mono", Consolas, monospace';
    ctx.fillStyle = "rgba(255, 255, 255, 0.24)";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("000", cx, cy - radius - 18);
    ctx.fillText("180", cx, cy + radius + 18);
    ctx.fillText("090", cx + radius + 16, cy);
    ctx.fillText("270", cx - radius - 16, cy);

    // Развёртка и метки направлений
    drawSweep(cx, cy, radius);
    const now = performance.now();
    blips.forEach((blip) => drawBlip(blip, cx, cy, radius, now));

    // Центр радара с мягким свечением
    const coreGlow = 0.5 + 0.5 * Math.sin(now / 900);
    ctx.beginPath();
    ctx.arc(cx, cy, 6 + coreGlow * 2, 0, TAU);
    ctx.fillStyle = "rgba(163, 230, 53, 0.9)";
    ctx.shadowColor = "rgba(163, 230, 53, 0.8)";
    ctx.shadowBlur = 16 + coreGlow * 10;
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  function hexToRgba(hex, alpha) {
    const clean = String(hex || "").replace("#", "");
    if (clean.length !== 6) return "rgba(148, 163, 184, " + alpha + ")";
    const value = parseInt(clean, 16);
    const red = (value >> 16) & 255;
    const green = (value >> 8) & 255;
    const blue = value & 255;
    return "rgba(" + red + "," + green + "," + blue + "," + alpha + ")";
  }

  function animate(timestamp) {
    if (lastFrame !== null) {
      const elapsed = Math.min(timestamp - lastFrame, 120); // защита от скачков при фокусе вкладки
      sweepAngle += (elapsed / FULL_TURN_MS) * TAU;
    }
    lastFrame = timestamp;
    draw();
    animationId = requestAnimationFrame(animate);
  }

  function start() {
    if (animationId !== null || reducedMotion) return;
    lastFrame = null;
    animationId = requestAnimationFrame(animate);
  }

  function stop() {
    if (animationId !== null) {
      cancelAnimationFrame(animationId);
      animationId = null;
    }
  }

  /* Запуск */
  resize();
  if (reducedMotion) {
    draw();
  } else {
    start();
  }

  window.addEventListener("resize", debounceResize);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
    else start();
  });

  let resizeTimer = null;
  function debounceResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resize, 150);
  }
})();
