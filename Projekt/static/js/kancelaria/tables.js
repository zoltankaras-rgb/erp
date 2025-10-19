// /static/js/kancelaria/tables.js
(function(){
  function isNumericText(txt){
    if (!txt) return false;
    const t = String(txt).trim().replace(/\s/g,'').replace(',', '.');
    return /^[-+]?(\d+(\.\d+)?|\.\d+)$/.test(t);
  }

  window.normalizeNumericTables = function normalizeNumericTables(root){
    const scope = root || document;
    scope.querySelectorAll('table.table').forEach(tbl=>{
      const thead = tbl.tHead;
      const tb = tbl.tBodies[0];
      if (!tb || !tb.rows || !tb.rows.length) return;

      const colCount = tb.rows[0].cells.length;
      for (let c = 0; c < colCount; c++){
        // stĺpec je číselný, ak v ňom aspoň jedna bunka má class="num" alebo obsahuje číslo
        let numeric = false;
        for (let r = 0; r < tb.rows.length; r++){
          const cell = tb.rows[r].cells[c];
          if (!cell) continue;
          if (cell.classList.contains('num')) { numeric = true; break; }
          const txt = cell.textContent || '';
          if (isNumericText(txt)) { numeric = true; break; }
        }
        if (numeric) {
          if (thead) {
            for (let r = 0; r < thead.rows.length; r++){
              if (thead.rows[r].cells[c]) thead.rows[r].cells[c].classList.add('num');
            }
          }
          // dorovnaj aj body (ak nie je)
          for (let r = 0; r < tb.rows.length; r++){
            const cell = tb.rows[r].cells[c];
            if (cell) cell.classList.add('num');
          }
        }
      }
    });
  };

  // spusti raz po načítaní stránky (pre statické tabuľky)
  document.addEventListener('DOMContentLoaded', ()=> window.normalizeNumericTables());
})();
