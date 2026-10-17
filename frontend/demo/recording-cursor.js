/* Recording-only pointer and frame marker. The ordinary app uses the system cursor. */
document.addEventListener('DOMContentLoaded', () => {
  const layer = document.createElement('div');
  layer.id = 'recording-layer'; layer.setAttribute('popover', 'manual');
  layer.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;max-width:none;max-height:none;margin:0;padding:0;border:0;background:transparent;overflow:hidden;pointer-events:none;z-index:2147483647;';
  const style = document.createElement('style');
  style.textContent = '@keyframes recording-ring{from{transform:translate(-50%,-50%) scale(.45);opacity:1}to{transform:translate(-50%,-50%) scale(1.7);opacity:0}}@keyframes recording-trail{to{opacity:0;transform:scale(.3)}}';
  layer.append(style);
  const marker = document.createElement('div');
  marker.id = 'recording-pace'; marker.style.cssText = 'position:fixed;left:0;top:0;width:10px;height:10px;background:#fff;';
  const cursor = document.createElement('div');
  cursor.id = 'recording-cursor';
  cursor.style.cssText = 'position:fixed;left:800px;top:180px;width:30px;height:34px;filter:drop-shadow(1px 2px 2px #112d4160);';
  cursor.innerHTML = '<svg width="30" height="34" viewBox="0 0 30 34"><path d="M3 2L3 27L10 21L16 32L21 29L15 19L25 18Z" fill="#214c3b" stroke="white" stroke-width="2" stroke-linejoin="round"/></svg>';
  layer.append(marker, cursor); document.body.append(layer); layer.showPopover();
  let lastTrail = 0;
  const bringToFront = () => {if (layer.matches(':popover-open')) layer.hidePopover(); layer.showPopover();};
  new MutationObserver(bringToFront).observe(document.getElementById('viewer'), {attributes:true, attributeFilter:['open']});
  document.addEventListener('mousemove', event => {
    cursor.style.left = `${event.clientX}px`; cursor.style.top = `${event.clientY}px`;
    if (performance.now() - lastTrail > 35) {
      lastTrail = performance.now();
      const dot = document.createElement('i');
      dot.style.cssText = `position:fixed;left:${event.clientX}px;top:${event.clientY}px;width:5px;height:5px;border-radius:50%;background:#db923e;opacity:.55;animation:recording-trail .55s linear forwards;`;
      layer.append(dot); setTimeout(() => dot.remove(), 600);
    }
  });
  document.addEventListener('mousedown', event => {
    const ring = document.createElement('div');
    ring.style.cssText = `position:fixed;left:${event.clientX}px;top:${event.clientY}px;width:44px;height:44px;border-radius:50%;border:3px solid #e29b41;background:#f6c56b22;animation:recording-ring .85s ease-out forwards;`;
    layer.append(ring); setTimeout(() => ring.remove(), 900);
  });
  window.demoRecording = {setIdle: idle => {marker.style.background = idle ? '#000' : '#fff';}};
});
