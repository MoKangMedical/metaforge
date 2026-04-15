/* ========================================
   MetaForge — 主脚本
   粒子动画、滚动效果、Demo交互
   ======================================== */

// === Particle System ===
class ParticleSystem {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.particles = [];
    this.connections = [];
    this.mouse = { x: 0, y: 0 };
    this.resize();
    this.init();
    window.addEventListener('resize', () => this.resize());
    window.addEventListener('mousemove', (e) => {
      this.mouse.x = e.clientX;
      this.mouse.y = e.clientY;
    });
  }

  resize() {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  }

  init() {
    const count = Math.min(80, Math.floor(window.innerWidth / 15));
    this.particles = [];
    for (let i = 0; i < count; i++) {
      this.particles.push({
        x: Math.random() * this.canvas.width,
        y: Math.random() * this.canvas.height,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        radius: Math.random() * 2 + 1,
        color: ['#3b82f6', '#8b5cf6', '#06b6d4', '#ec4899'][Math.floor(Math.random() * 4)],
        alpha: Math.random() * 0.5 + 0.2,
      });
    }
  }

  update() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    for (const p of this.particles) {
      p.x += p.vx;
      p.y += p.vy;

      // Mouse repulsion
      const dx = p.x - this.mouse.x;
      const dy = p.y - this.mouse.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 150) {
        const force = (150 - dist) / 150;
        p.vx += (dx / dist) * force * 0.2;
        p.vy += (dy / dist) * force * 0.2;
      }

      // Boundaries
      if (p.x < 0 || p.x > this.canvas.width) p.vx *= -1;
      if (p.y < 0 || p.y > this.canvas.height) p.vy *= -1;

      // Damping
      p.vx *= 0.99;
      p.vy *= 0.99;

      // Draw particle
      this.ctx.beginPath();
      this.ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      this.ctx.fillStyle = p.color;
      this.ctx.globalAlpha = p.alpha;
      this.ctx.fill();
    }

    // Draw connections
    this.ctx.globalAlpha = 1;
    for (let i = 0; i < this.particles.length; i++) {
      for (let j = i + 1; j < this.particles.length; j++) {
        const a = this.particles[i];
        const b = this.particles[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) {
          this.ctx.beginPath();
          this.ctx.moveTo(a.x, a.y);
          this.ctx.lineTo(b.x, b.y);
          this.ctx.strokeStyle = `rgba(59, 130, 246, ${0.15 * (1 - dist / 120)})`;
          this.ctx.lineWidth = 0.5;
          this.ctx.stroke();
        }
      }
    }

    requestAnimationFrame(() => this.update());
  }
}

// === Scroll Reveal ===
function initScrollReveal() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

  document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
}

// === Counter Animation ===
function animateCounters() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const el = entry.target;
        const target = parseInt(el.dataset.target);
        const suffix = el.dataset.suffix || '';
        const prefix = el.dataset.prefix || '';
        let current = 0;
        const step = target / 60;
        const timer = setInterval(() => {
          current += step;
          if (current >= target) {
            current = target;
            clearInterval(timer);
          }
          el.textContent = prefix + Math.floor(current).toLocaleString() + suffix;
        }, 16);
        observer.unobserve(el);
      }
    });
  }, { threshold: 0.5 });

  document.querySelectorAll('.counter').forEach(el => observer.observe(el));
}

// === Navigation Scroll Effect ===
function initNav() {
  const nav = document.querySelector('.nav');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 50) {
      nav.classList.add('scrolled');
    } else {
      nav.classList.remove('scrolled');
    }
  });

  // Active link highlighting
  const sections = document.querySelectorAll('.page-section');
  const links = document.querySelectorAll('.nav-links a');

  window.addEventListener('scroll', () => {
    let current = '';
    sections.forEach(section => {
      const top = section.offsetTop - 120;
      if (window.scrollY >= top) {
        current = section.getAttribute('id');
      }
    });
    links.forEach(link => {
      link.classList.remove('active');
      if (link.getAttribute('href') === '#' + current) {
        link.classList.add('active');
      }
    });
  });
}

// === Demo Terminal Animation ===
function initDemo() {
  const terminal = document.getElementById('demo-terminal');
  if (!terminal) return;

  const lines = [
    { type: 'prompt', content: '$ metaforge init --project "PD-1抑制剂联合化疗治疗NSCLC的Meta分析"' },
    { type: 'output', content: '🔧 初始化MetaForge项目引擎...' },
    { type: 'success', content: '✓ 项目创建成功 | ID: MF-2026-0415-001' },
    { type: 'output', content: '' },
    { type: 'prompt', content: '$ metaforge search --databases pubmed,cochrane,embase,cnki --auto-expand' },
    { type: 'info', content: '📡 Agent-Seeker 正在连接数据库...' },
    { type: 'output', content: '  ├─ PubMed ━━━━━━━━━━━━━ 2,847 篇' },
    { type: 'output', content: '  ├─ Cochrane ━━━━━━━━━━━━ 423 篇' },
    { type: 'output', content: '  ├─ Embase ━━━━━━━━━━━━━━ 1,956 篇' },
    { type: 'output', content: '  └─ CNKI ━━━━━━━━━━━━━━━━ 312 篇' },
    { type: 'success', content: '✓ 去重完成：总计 3,821 → 去重后 2,947 篇 (去重率 22.9%)' },
    { type: 'output', content: '' },
    { type: 'prompt', content: '$ metaforge screen --ai-model gpt-4o --parallel 16' },
    { type: 'info', content: '🔍 Agent-Filter 开始智能筛选 (16线程并行)...' },
    { type: 'output', content: '  初筛 (标题/摘要): ████████████████████ 100% | 2,947 → 486 篇' },
    { type: 'output', content: '  全文筛选:          ████████████████████ 100% | 486 → 52 篇' },
    { type: 'success', content: '✓ PRISMA流程图已自动生成' },
    { type: 'output', content: '' },
    { type: 'prompt', content: '$ metaforge extract --template cochrane-rob2 --parallel 8' },
    { type: 'info', content: '📊 Agent-Extractor 开始数据提取...' },
    { type: 'output', content: '  提取进度: ████████████████████ 100% | 52/52 研究完成' },
    { type: 'success', content: '✓ 提取 312 个数据点 | 质量评价完成 (RoB 2.0)' },
    { type: 'output', content: '' },
    { type: 'prompt', content: '$ metaforge analyze --model random-effects --subgroup age,region,dosage' },
    { type: 'info', content: '🧮 Agent-Analyst 执行统计分析...' },
    { type: 'output', content: '  合并效应量 (OR): 1.87 [95% CI: 1.42-2.46]' },
    { type: 'output', content: '  异质性 I²: 34.2% (p=0.08) → 低度异质性 ✓' },
    { type: 'output', content: '  亚组分析: 年龄(p=0.03), 地区(p=0.12), 剂量(p=0.01)' },
    { type: 'success', content: '✓ 森林图、漏斗图、敏感性分析已生成' },
    { type: 'output', content: '' },
    { type: 'prompt', content: '$ metaforge report --format prisma-2020 --lang zh,en' },
    { type: 'info', content: '📝 Agent-Writer 生成研究报告...' },
    { type: 'output', content: '  ├─ PRISMA 2020 结构化报告 ✓' },
    { type: 'output', content: '  ├─ 中英文双语报告 ✓' },
    { type: 'output', content: '  ├─ 参考文献格式化 (Vancouver) ✓' },
    { type: 'output', content: '  └─ GRADE 证据质量评级 ✓' },
    { type: 'success', content: '🎉 全流程完成！总耗时: 47分钟 (传统方式: 45-90天)' },
    { type: 'output', content: '' },
    { type: 'info', content: '📎 输出文件:' },
    { type: 'output', content: '  • report_zh.pdf (3.2 MB)' },
    { type: 'output', content: '  • report_en.pdf (2.8 MB)' },
    { type: 'output', content: '  • prisma_flowchart.svg' },
    { type: 'output', content: '  • forest_plot.png / funnel_plot.png' },
    { type: 'output', content: '  • supplementary_data.xlsx' },
  ];

  let lineIndex = 0;
  const body = terminal.querySelector('.demo-terminal-body');

  function addLine() {
    if (lineIndex >= lines.length) {
      // Loop after a pause
      setTimeout(() => {
        body.innerHTML = '';
        lineIndex = 0;
        addLine();
      }, 5000);
      return;
    }

    const line = lines[lineIndex];
    const div = document.createElement('div');
    div.className = 'demo-line';
    div.style.animationDelay = '0s';

    switch (line.type) {
      case 'prompt':
        div.innerHTML = `<span class="prompt">$</span> <span class="cmd">${line.content.substring(2)}</span>`;
        break;
      case 'success':
        div.innerHTML = `<span class="success">${line.content}</span>`;
        break;
      case 'info':
        div.innerHTML = `<span class="info">${line.content}</span>`;
        break;
      case 'error':
        div.innerHTML = `<span class="error">${line.content}</span>`;
        break;
      default:
        div.innerHTML = `<span class="output">${line.content}</span>`;
    }

    body.appendChild(div);
    body.scrollTop = body.scrollHeight;
    lineIndex++;

    const delay = line.content === '' ? 100 : (line.type === 'prompt' ? 600 : 200);
    setTimeout(addLine, delay);
  }

  // Start demo when visible
  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) {
      addLine();
      observer.disconnect();
    }
  }, { threshold: 0.3 });
  observer.observe(terminal);
}

// === Typing Effect ===
function typeWriter(element, text, speed = 50) {
  let i = 0;
  element.textContent = '';
  function type() {
    if (i < text.length) {
      element.textContent += text.charAt(i);
      i++;
      setTimeout(type, speed);
    }
  }
  type();
}

// === Mobile Menu ===
function initMobileMenu() {
  const btn = document.querySelector('.mobile-menu-btn');
  const links = document.querySelector('.nav-links');
  if (!btn || !links) return;

  btn.addEventListener('click', () => {
    links.style.display = links.style.display === 'flex' ? 'none' : 'flex';
    links.style.position = 'absolute';
    links.style.top = '100%';
    links.style.left = '0';
    links.style.right = '0';
    links.style.flexDirection = 'column';
    links.style.background = 'rgba(10, 14, 26, 0.98)';
    links.style.padding = '20px';
    links.style.gap = '16px';
    links.style.borderBottom = '1px solid rgba(255,255,255,0.06)';
  });
}

// === Smooth Scroll for Nav Links ===
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const target = document.querySelector(link.getAttribute('href'));
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });
}

// === Comparison Table Hover ===
function initComparison() {
  const rows = document.querySelectorAll('.comparison-table tbody tr');
  rows.forEach(row => {
    row.addEventListener('mouseenter', () => {
      row.style.background = 'rgba(59, 130, 246, 0.05)';
    });
    row.addEventListener('mouseleave', () => {
      row.style.background = '';
    });
  });
}

// === Initialize Everything ===
document.addEventListener('DOMContentLoaded', () => {
  // Particle system
  const canvas = document.getElementById('hero-canvas');
  if (canvas) {
    const ps = new ParticleSystem(canvas);
    ps.update();
  }

  initScrollReveal();
  animateCounters();
  initNav();
  initDemo();
  initMobileMenu();
  initSmoothScroll();
  initComparison();
});
