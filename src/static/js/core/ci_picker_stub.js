window.app = window.app || {};
(function(){
  if (window.ciPicker) return;

  const stub = {
    open:false, q:'', typePath:'', loading:false, items:[], next:null, uiNonce:0,
    onPick:(it)=>{},

    openWith(typePath=''){ this.typePath = typePath || ''; this.open = true; },
    async search(){ this.items=[]; this.next=null; },
    async more(){},

    pairsFor(){ return []; },
    pick(it){ this.onPick(it); this.open=false; },
    close(){ this.open=false; },
    show(){ this.open=true; }
  };

  window.ciPicker = stub;

  document.addEventListener('alpine:init', () => {
    try {
      const s = Alpine.store('ciPicker');
      if (s) Object.assign(s, stub);
      else Alpine.store('ciPicker', stub);
    } catch {}
  });
})();
