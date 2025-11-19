/* lightweight particles init (no external library) */
function particlesJS(id, config) {
  // very small particles effect: create random dots canvas
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = '';
  const canvas = document.createElement('canvas');
  el.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  window.addEventListener('resize', () => {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  });

  const count = (config && config.particles && config.particles.number && config.particles.number.value) || 40;
  const particles = [];
  for (let i=0;i<count;i++){
    particles.push({
      x: Math.random()*canvas.width,
      y: Math.random()*canvas.height,
      r: (config.particles.size && config.particles.size.value) ? config.particles.size.value*Math.random()+1 : 2,
      vx: (Math.random()-0.5)*0.5,
      vy: (Math.random()-0.5)*0.5,
      alpha: 0.2 + Math.random()*0.6
    });
  }

  function frame(){
    ctx.clearRect(0,0,canvas.width,canvas.height);
    particles.forEach(p=>{
      p.x += p.vx;
      p.y += p.vy;
      if (p.x<0) p.x = canvas.width;
      if (p.x>canvas.width) p.x = 0;
      if (p.y<0) p.y = canvas.height;
      if (p.y>canvas.height) p.y = 0;
      ctx.beginPath();
      ctx.fillStyle = `rgba(255,255,255,${p.alpha})`;
      ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.fill();
    });
    requestAnimationFrame(frame);
  }
  frame();
}
