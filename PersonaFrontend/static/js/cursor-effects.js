/**
 * CURSOR & INTERACTION EFFECTS
 * Premium cursor effects for marketing pages only
 * Disabled on mobile/touch devices and for reduced-motion users
 */

(function() {
  'use strict';

  // ============================================
  // DETECTION: Mobile & Reduced Motion
  // ============================================
  const isTouchDevice = window.matchMedia('(pointer: coarse)').matches;
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Exit early if touch device or reduced motion preferred
  if (isTouchDevice || prefersReducedMotion) {
    return;
  }

  // ============================================
  // CUSTOM CURSOR (Dual-cursor pattern)
  // ============================================
  const cursorDot = document.createElement('div');
  const cursorRing = document.createElement('div');

  // Style the cursor dot (small, follows immediately)
  cursorDot.className = 'cursor-dot';
  cursorDot.style.cssText = `
    position: fixed;
    width: 8px;
    height: 8px;
    background-color: var(--color-primary, #6366f1);
    border-radius: 50%;
    pointer-events: none;
    z-index: 9999;
    will-change: transform;
    transform: translate(-50%, -50%);
  `;

  // Style the cursor ring (larger, follows with lag)
  cursorRing.className = 'cursor-ring';
  cursorRing.style.cssText = `
    position: fixed;
    width: 40px;
    height: 40px;
    border: 2px solid var(--color-primary, #6366f1);
    border-radius: 50%;
    pointer-events: none;
    z-index: 9998;
    will-change: transform;
    transform: translate(-50%, -50%);
    transition: width 0.2s ease, height 0.2s ease, border-color 0.2s ease;
  `;

  document.body.appendChild(cursorDot);
  document.body.appendChild(cursorRing);

  // Cursor position tracking
  let mouseX = 0;
  let mouseY = 0;
  let ringX = 0;
  let ringY = 0;
  const ringSpeed = 0.15; // Lag factor for smooth following

  // Track mouse position
  document.addEventListener('mousemove', (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
  });

  // Hide cursor when leaving window
  document.addEventListener('mouseleave', () => {
    cursorDot.style.opacity = '0';
    cursorRing.style.opacity = '0';
  });

  document.addEventListener('mouseenter', () => {
    cursorDot.style.opacity = '1';
    cursorRing.style.opacity = '1';
  });

  // Animation loop for smooth cursor movement (60fps)
  function animateCursor() {
    // Dot follows immediately
    cursorDot.style.transform = `translate(${mouseX}px, ${mouseY}px) translate(-50%, -50%)`;

    // Ring follows with easing
    ringX += (mouseX - ringX) * ringSpeed;
    ringY += (mouseY - ringY) * ringSpeed;
    cursorRing.style.transform = `translate(${ringX}px, ${ringY}px) translate(-50%, -50%)`;

    requestAnimationFrame(animateCursor);
  }

  animateCursor();

  // ============================================
  // CURSOR HOVER EFFECTS
  // ============================================
  const interactiveSelectors = [
    'a',
    'button',
    'input[type="submit"]',
    'input[type="button"]',
    '.btn',
    '.btn-primary',
    '.btn-secondary',
    '.btn-ghost',
    '[role="button"]',
    '.interactive'
  ];

  const interactiveElements = document.querySelectorAll(interactiveSelectors.join(', '));

  interactiveElements.forEach(element => {
    element.addEventListener('mouseenter', () => {
      cursorRing.style.width = '60px';
      cursorRing.style.height = '60px';
      cursorRing.style.borderColor = 'var(--color-accent, #8b5cf6)';
      cursorDot.style.transform = `translate(${mouseX}px, ${mouseY}px) translate(-50%, -50%) scale(1.5)`;
    });

    element.addEventListener('mouseleave', () => {
      cursorRing.style.width = '40px';
      cursorRing.style.height = '40px';
      cursorRing.style.borderColor = 'var(--color-primary, #6366f1)';
      cursorDot.style.transform = `translate(${mouseX}px, ${mouseY}px) translate(-50%, -50%) scale(1)`;
    });
  });

  // ============================================
  // MAGNETIC BUTTON EFFECT
  // ============================================
  const magneticButtonSelectors = [
    '.btn-primary',
    '.btn-secondary',
    '.magnetic-btn',
    'a[href="/signup/"]',
    'a[href*="signup"]',
    'a[href*="login"]'
  ];

  const magneticButtons = document.querySelectorAll(magneticButtonSelectors.join(', '));

  magneticButtons.forEach(button => {
    button.addEventListener('mousemove', (e) => {
      const rect = button.getBoundingClientRect();
      const x = e.clientX - rect.left - rect.width / 2;
      const y = e.clientY - rect.top - rect.height / 2;

      // Magnetic pull strength (subtle)
      const strength = 0.3;
      
      button.style.transform = `translate(${x * strength}px, ${y * strength}px)`;
    });

    button.addEventListener('mouseleave', () => {
      button.style.transform = 'translate(0, 0)';
    });
  });

  // ============================================
  // SUBTLE BACKGROUND GLOW EFFECT
  // ============================================
  const heroSection = document.querySelector('.hero-section, section:first-of-type');
  
  if (heroSection) {
    const glowElement = document.createElement('div');
    glowElement.className = 'cursor-glow';
    glowElement.style.cssText = `
      position: absolute;
      width: 400px;
      height: 400px;
      background: radial-gradient(circle, rgba(99, 102, 241, 0.08) 0%, transparent 70%);
      border-radius: 50%;
      pointer-events: none;
      z-index: 0;
      will-change: transform;
      transform: translate(-50%, -50%);
      transition: opacity 0.3s ease;
    `;

    heroSection.style.position = 'relative';
    heroSection.style.overflow = 'hidden';
    heroSection.appendChild(glowElement);

    let glowX = 0;
    let glowY = 0;

    heroSection.addEventListener('mousemove', (e) => {
      const rect = heroSection.getBoundingClientRect();
      glowX = e.clientX - rect.left;
      glowY = e.clientY - rect.top;
    });

    heroSection.addEventListener('mouseenter', () => {
      glowElement.style.opacity = '1';
    });

    heroSection.addEventListener('mouseleave', () => {
      glowElement.style.opacity = '0';
    });

    // Animate glow with easing
    let currentGlowX = 0;
    let currentGlowY = 0;
    const glowSpeed = 0.1;

    function animateGlow() {
      currentGlowX += (glowX - currentGlowX) * glowSpeed;
      currentGlowY += (glowY - currentGlowY) * glowSpeed;
      glowElement.style.transform = `translate(${currentGlowX}px, ${currentGlowY}px) translate(-50%, -50%)`;
      requestAnimationFrame(animateGlow);
    }

    animateGlow();
  }

  // ============================================
  // CLEANUP ON PAGE UNLOAD
  // ============================================
  window.addEventListener('beforeunload', () => {
    cursorDot.remove();
    cursorRing.remove();
  });

  console.log('✨ Cursor effects loaded (marketing pages only)');
})();
