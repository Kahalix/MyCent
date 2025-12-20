window.app = window.app || {};
(function(){
  if (window.ciPicker) return;
  const stub = { open:false, q:'', items:[], loading:false, next:null, typePath:'',
    search(){}, more(){}, show(){this.open=true}, close(){this.open=false}
  };
  window.ciPicker = stub;
  document.addEventListener('alpine:init', () => {
    try { if (!Alpine.store('ciPicker')) Alpine.store('ciPicker', stub); } catch {}
  });
})();