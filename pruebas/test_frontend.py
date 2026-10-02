"""Pruebas del frontend en Chrome headless (Playwright) — flujo de aprobaciones y perfiles.

Carga frontend/bitacora-obra.html con una base simulada que imita las reglas del artifact:
  lectura nivel Lector:  contratos, unidades, hitos, oficial
  lectura Colaborador+:  todo lo demás (audit/<cuenta>: solo la propia o Editor)
  escritura Editor:      contratos, unidades, hitos, oficial, permisos, config, credenciales
  escritura propia:      audit/<cuenta>
Escenarios: IF, Validador, Gabinete, Administrador y cuenta sin perfil.

Ejecutar:  python test_frontend.py
"""
import datetime as dt
import hashlib
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

AQUI = pathlib.Path(__file__).resolve().parent
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PAGINA = (AQUI.parent / 'frontend' / 'bitacora-obra.html').read_text(encoding='utf-8')
XSS = '<img src=x onerror="window.__T.xss++">'
HOY = dt.date.today()


def d(dias):
    return (HOY + dt.timedelta(days=dias)).isoformat()


FAKE_RUNTIME = r"""
window.__T = { writes: [], queries: [], listeners: 0, xss: 0 };
(function(){
  var cfg = window.__TCFG, store = new Map(), listeners = new Set(), idc = 0;
  Object.keys(cfg.seed).forEach(function(k){ store.set(k, JSON.parse(JSON.stringify(cfg.seed[k]))); });
  var NIVEL = { view:0, interact:1, admin:2 }[cfg.level];
  var LECTURA_PUBLICA = ['contratos', 'unidades', 'hitos', 'oficial'];
  var SOLO_EDITOR = ['contratos', 'unidades', 'hitos', 'oficial', 'permisos', 'config', 'credenciales'];
  function clone(x){ return x === undefined ? undefined : JSON.parse(JSON.stringify(x)); }
  function puedeLeer(path){
    var s = path.split('/');
    if(s[0] === 'audit') return s[1] === cfg.uid || NIVEL === 2;
    if(s[0] === 'credenciales') return NIVEL === 2;
    if(LECTURA_PUBLICA.indexOf(s[0]) !== -1) return true;
    return NIVEL >= 1;
  }
  function puedeEscribir(path){
    var s = path.split('/');
    if(SOLO_EDITOR.indexOf(s[0]) !== -1) return NIVEL === 2;
    if(s[0] === 'audit') return s[1] === cfg.uid && NIVEL >= 1;
    return NIVEL >= 1;
  }
  function rechazo(){ var e = new Error('invalid_argument'); e.code = 'invalid_argument'; return Promise.reject(e); }
  function snapDoc(path){ var d = store.get(path), ok = d !== undefined && puedeLeer(path); return { id: path.split('/').pop(), exists: ok, data: function(){ return ok ? clone(d) : undefined; }, metadata:{fromCache:false, hasPendingWrites:false} }; }
  function avisar(){ listeners.forEach(function(l){ setTimeout(l.fire, 0); }); }
  function escuchar(fire){
    var l = { fire: function(){ if(!l.muerto) fire(); } };
    listeners.add(l); window.__T.listeners = listeners.size; setTimeout(l.fire, 0);
    return function(){ l.muerto = true; listeners.delete(l); window.__T.listeners = listeners.size; };
  }
  function cumple(d, f){ if(f[1] === '==') return d[f[0]] === f[2]; if(f[1] === 'in') return f[2].indexOf(d[f[0]]) !== -1; return true; }
  function query(col, filtros, orden, lim){
    function correr(){
      var pref = col + '/', n = col.split('/').length + 1, docs = [];
      store.forEach(function(d, p){ if(p.indexOf(pref) === 0 && p.split('/').length === n && puedeLeer(p) && filtros.every(function(f){ return cumple(d, f); })) docs.push(snapDoc(p)); });
      if(orden) docs.sort(function(a, b){ var x = a.data()[orden[0]], y = b.data()[orden[0]]; if(x === undefined) return 1; if(y === undefined) return -1; return (x < y ? -1 : x > y ? 1 : 0) * (orden[1] === 'desc' ? -1 : 1); });
      if(lim) docs = docs.slice(0, lim);
      return { docs: docs, size: docs.length, empty: !docs.length, docChanges: function(){ return []; }, metadata:{fromCache:false, hasPendingWrites:false} };
    }
    return {
      where: function(f, op, v){ return query(col, filtros.concat([[f, op, v]]), orden, lim); },
      orderBy: function(f, dir){ return query(col, filtros, [f, dir || 'asc'], lim); },
      limit: function(n){ return query(col, filtros, orden, n); },
      get: function(){ return Promise.resolve(correr()); },
      onSnapshot: function(next){ window.__T.queries.push({col: col, filtros: filtros}); return escuchar(function(){ next(correr()); }); }
    };
  }
  function docRef(path){
    return {
      id: path.split('/').pop(), path: path,
      get: function(){ return Promise.resolve(snapDoc(path)); },
      set: function(data){ if(!puedeEscribir(path)) return rechazo(); window.__T.writes.push({op:'set', path:path, data:clone(data)}); store.set(path, clone(data)); avisar(); return Promise.resolve(); },
      update: function(data){ if(!puedeEscribir(path) || !store.has(path)) return rechazo(); window.__T.writes.push({op:'update', path:path, data:clone(data)}); store.set(path, Object.assign(clone(store.get(path)), clone(data))); avisar(); return Promise.resolve(); },
      delete: function(){ window.__T.writes.push({op:'delete', path:path}); store.delete(path); avisar(); return Promise.resolve(); },
      onSnapshot: function(next){ window.__T.queries.push({col: path, filtros: []}); return escuchar(function(){ next(snapDoc(path)); }); },
      collection: function(sub){ return colRef(path + '/' + sub); }
    };
  }
  function colRef(col){
    var q = query(col, [], null, null);
    q.path = col;
    q.doc = function(id){ return docRef(col + '/' + (id || ('auto' + (++idc) + 'x'))); };
    q.add = function(data){ var r = q.doc(); return r.set(data).then(function(){ return r; }); };
    return q;
  }
  var dir = cfg.directory || [];
  var userApi = {
    canEdit: async function(){ return NIVEL === 2; },
    can: async function(){ return NIVEL >= 1; },
    me: async function(){ return { id: cfg.uid, name: cfg.name, email: null, isOwner: false, canEdit: NIVEL === 2, avatarUrl: '', color: '' }; },
    id: async function(){ return cfg.uid; },
    profiles: async function(ids){ var o = {}; [].concat(ids).forEach(function(i){ var p = dir.filter(function(x){ return x.id === i; })[0]; o[i] = { id: i, name: p ? p.name : '', avatarUrl: '', color: '', email: null, isMe: i === cfg.uid, guest: false }; }); return o; },
    search: async function(q){ q = (q || '').toLowerCase(); return dir.filter(function(x){ return x.name.toLowerCase().indexOf(q) !== -1; }).slice(0, 8).map(function(x){ return { id: x.id, name: x.name, avatarUrl: '', color: '', email: null, isMe: false, guest: false }; }); }
  };
  window.claude = { use: async function(n){ return n === 'db' ? { doc: docRef, collection: colRef } : (n === 'user' ? userApi : null); } };
})();
"""


def canon(lista):
    return json.dumps(lista, ensure_ascii=False, separators=(',', ':'))


def sha(texto):
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


DIRECTORIO = [{'id': 'u_if1', 'name': 'Inés Fiscal'}, {'id': 'u_val', 'name': 'Valentina Jefa'},
              {'id': 'u_if2', 'name': 'Ana Pérez'}, {'id': 'u_admin', 'name': 'Admin Central'}]


def base():
    s = {
        'contratos/c1': {'nombre': 'Red Aeroportuaria Austral', 'unidadLabel': 'Aeropuerto', 'inspectorNombre': 'Inés Fiscal'},
        'contratos/c2': {'nombre': 'Teleférico Bicentenario', 'unidadLabel': 'Estación', 'inspectorNombre': 'Otro IF'},
        'unidades/u1': {'contratoId': 'c1', 'nombre': 'Aeródromo ' + XSS, 'activo': True},
        'unidades/u2': {'contratoId': 'c2', 'nombre': 'SECRETO-C2-UNIDAD', 'activo': True},
        'hitos/h1': {'contratoId': 'c1', 'unidadId': 'u1', 'nombre': 'Ingeniería definitiva', 'tipo': 'Ingeniería', 'fechaContractual': d(-60)},
        'hitos/h2': {'contratoId': 'c1', 'unidadId': 'u1', 'nombre': 'Inicio de obras ' + XSS, 'tipo': 'Inicio Físico', 'fechaContractual': d(20)},
        'hitos/h3': {'contratoId': 'c1', 'unidadId': 'u1', 'nombre': 'PSP', 'tipo': 'PSP', 'fechaContractual': d(200)},
        'hitos/h9': {'contratoId': 'c2', 'unidadId': 'u2', 'nombre': 'SECRETO-C2-HITO', 'tipo': 'PSP', 'fechaContractual': d(100)},
        'oficial/avance-u1': {'tipo': 'avance', 'contratoId': 'c1', 'unidadId': 'u1', 'valor': 62, 'fechaReporte': d(-10), 'aprobadoTs': 1790000000000},
        'oficial/hito-h1': {'tipo': 'hito', 'contratoId': 'c1', 'hitoId': 'h1', 'fechaVigente': d(-60), 'fechaReal': d(-55), 'aprobadoTs': 1790000000000},
        'oficial/hist-x1': {'tipo': 'historial', 'contratoId': 'c1', 'campo': 'avance', 'ref': 'u1', 'valorAnterior': 50, 'valorNuevo': 62,
                            'fechaReporte': d(-10), 'nota': 'Nota aprobada ' + XSS, 'autorId': 'u_if1', 'revisorId': 'u_val', 'aprobadoTs': 1790000000000},
        'oficial/alerta-pz': {'tipo': 'alerta', 'contratoId': 'c1', 'problematicaId': 'pz', 'titulo': 'Alerta publicada ' + XSS, 'nivelRiesgo': 'Extremo',
                              'escalamiento': ['Directora'], 'estado': 'escalado', 'publicadoTs': 1790000000000, 'isDeleted': False},
        'oficial/alerta-pq': {'tipo': 'alerta', 'contratoId': 'c1', 'problematicaId': 'pq', 'titulo': 'ALERTA-RETIRADA', 'nivelRiesgo': 'Alto',
                              'escalamiento': [], 'estado': 'escalado', 'publicadoTs': 1790000000000, 'isDeleted': True},
        'solicitudes/sx': {'tipo': 'avance', 'contratoId': 'c2', 'unidadId': 'u2', 'valorPropuesto': 99, 'estado': 'PENDIENTE_APROBACION',
                           'nota': 'SECRETO-C2-SOLICITUD', 'autorId': 'u_otro', 'creadoTs': 1790000000000, 'enviadoTs': 1790000000000},
        'problematicas/p2': {'contratoId': 'c2', 'titulo': 'SECRETO-C2-PB', 'descripcion': 'd', 'estado': 'detectado', 'ts': 4},
        'permisos/u_if1': {'rol': 'if', 'contratos': ['c1'], 'activo': True},
        'permisos/u_val': {'rol': 'validador', 'contratos': ['c1'], 'activo': True},
    }
    return s


resultados = []


def check(nombre, cond, detalle=''):
    resultados.append((nombre, bool(cond)))
    print(('  OK    ' if cond else '  FALLA ') + nombre + ('' if cond else '  -> ' + str(detalle)[:400]))


def abrir(p, cfg):
    cfg.setdefault('directory', DIRECTORIO)
    tmp = AQUI / '_tmp_prueba.html'
    cfg_js = json.dumps(cfg).replace('</', '<\\/')
    tmp.write_text('<meta charset="utf-8"><script>window.__TCFG = ' + cfg_js + ';</script><script>' + FAKE_RUNTIME
                   + '</script>\n' + PAGINA, encoding='utf-8')
    browser = p.chromium.launch(executable_path=CHROME, headless=True)
    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    errores = []
    page.on('pageerror', lambda e: errores.append(str(e)))
    page.goto(tmp.as_uri())
    return browser, page, errores


def escrituras(page):
    return page.evaluate('window.__T.writes')


def esperar(page, prefijo, n):
    page.wait_for_function('([p, n]) => window.__T.writes.slice(n).some(w => w.path.startsWith(p))', arg=[prefijo, n], timeout=15000)
    return escrituras(page)[n:]


def toast(page):
    page.wait_for_timeout(250)
    return page.inner_text('#toast')


def ingresar(page):
    page.wait_for_selector('#gateBtn', state='visible', timeout=15000)
    page.click('#gateBtn')
    page.wait_for_selector('#appShell', state='visible', timeout=15000)
    page.wait_for_timeout(400)


def tab(page, nombre):
    page.click(f'#tabsNav [data-tab={nombre}]')
    page.wait_for_timeout(250)


def escenario_if(p):
    print('\nA. Inspector Fiscal (Colaborador, contrato c1)')
    seed = base()
    seed['problematicas/p1'] = {'contratoId': 'c1', 'unidadId': 'u1', 'titulo': XSS, 'descripcion': '<script>window.__T.xss++</script>',
                                'escalamiento': 'Directora', 'estado': 'detectado', 'nivelRiesgo': '__proto__', 'ts': 3,
                                'bitacora': [{'texto': XSS, 'autor': '<b>z</b>'}], 'checklist': [{'texto': XSS, 'hecho': False}]}
    browser, page, errores = abrir(p, {'uid': 'u_if1', 'name': 'Inés Fiscal', 'level': 'interact', 'seed': seed})
    try:
        page.wait_for_selector('#gatePerfil', state='visible', timeout=15000)
        txt = page.inner_text('#gatePerfilBox')
        check('Ingreso muestra la cuenta, el perfil y los contratos asignados', 'Inés Fiscal' in txt and 'Inspector Fiscal' in txt and 'Red Aeroportuaria Austral' in txt, txt)
        ingresar(page)
        qs = page.evaluate('window.__T.queries')
        ops = [q for q in qs if q['col'] in ('solicitudes', 'problematicas')]
        check('Datos operativos consultados solo de su contrato', len(ops) == 2 and all(q['filtros'] == [['contratoId', '==', 'c1']] for q in ops), ops)
        check('El IF no consulta permisos, auditoría ni configuración', not any(q['col'].startswith(('permisos', 'audit', 'config')) for q in qs), qs)
        check('Selector "Ver como" oculto para el IF', page.is_hidden('#verComoWrap'))
        tab_ids = page.eval_on_selector_all('#tabsNav .tabd', 'els => els.map(e => e.dataset.tab)')
        check('Pestañas del IF', tab_ids == ['contratos', 'cargar', 'solicitudes', 'problematicas', 'resueltas'], tab_ids)
        page.click('.ccard[data-cid=c1] .js-radar')
        page.wait_for_timeout(300)
        pasos = page.eval_on_selector_all('.ccard[data-cid=c1] .rstep', 'els => els.map(e => e.className)')
        check('Radar: Ingeniería cumplida, Inicio Físico crítico, PSP futura, PSD sin hito',
              pasos == ['rstep done', 'rstep crit', 'rstep fut', 'rstep none'], pasos)
        check('Radar crítico muestra días restantes', 'Faltan 20 d' in page.inner_text('.ccard[data-cid=c1] .rstep.crit'))
        check('Desglose del cronograma desplegado al hacer clic', page.locator('.ccard[data-cid=c1] .acc table').count() == 1)
        page.click('.ccard[data-cid=c1] .js-hist')
        page.wait_for_timeout(200)
        check('Bitácora histórica con el cambio aprobado', '50% → 62%' in page.inner_text('.ccard[data-cid=c1] .hist'))

        tab(page, 'cargar')
        n = len(escrituras(page))
        page.select_option('#cgAvUnidad', 'u1')
        page.fill('#cgAvPct', '150')
        page.click('#formAvance button[type=submit]')
        check('Avance fuera de rango rechazado', 'entre 0 y 100' in toast(page) and len(escrituras(page)) == n)
        page.fill('#cgAvPct', '70')
        page.fill('#cgAvNota', 'Avance de pavimentos')
        page.click('#formAvance button[type=submit]')
        nuevas = esperar(page, 'solicitudes/', n)
        rec = next(w for w in nuevas if w['path'].startswith('audit/'))
        sol = next(w for w in nuevas if w['path'].startswith('solicitudes/'))
        s = sol['data']
        check('Solicitud creada en revisión, con vigente al proponer y autoría de sesión',
              s['estado'] == 'PENDIENTE_APROBACION' and s['valorPropuesto'] == 70 and s['valorVigente'] == 62 and s['autorId'] == 'u_if1' and s['contratoId'] == 'c1', s)
        esperado = sha(canon(['solicitud', s['tipo'], s['contratoId'], s['unidadId'], s['valorPropuesto'], s['fechaReporte'], s['nota'], s['autorId'], s['creadoTs']]))
        check('Recibo antes de la solicitud y hash compatible con Python', nuevas.index(rec) < nuevas.index(sol) and rec['data']['hash'] == esperado)
        page.fill('#cgAvPct', '75')
        page.click('#formAvance button[type=submit]')
        check('No permite dos propuestas activas para el mismo dato', 'Ya hay una solicitud activa' in toast(page))

        n = len(escrituras(page))
        page.select_option('#cgHito', 'h2')
        page.fill('#cgFecha', d(40))
        page.click('#formFecha button[type=submit]')
        check('Reprogramar exige justificación', 'Justifica' in toast(page) and len(escrituras(page)) == n)
        page.fill('#cgFechaNota', 'Retraso en permisos')
        page.click('#formFecha [data-borrador]')
        nuevas = esperar(page, 'solicitudes/', n)
        check('Borrador guardado', next(w for w in nuevas if w['path'].startswith('solicitudes/'))['data']['estado'] == 'BORRADOR')

        tab(page, 'solicitudes')
        check('Mis solicitudes muestra días en revisión', 'En revisión hace 0 días' in page.inner_text('#solLista'))
        page.click('#solFiltros [data-filtro=BORRADOR]')
        n = len(escrituras(page))
        page.click('#solLista .js-sol-cancelar')
        page.click('#solLista .js-sol-cancelar-si')
        nuevas = esperar(page, 'solicitudes/', n)
        check('Cancelar borrador = eliminación lógica (sin borrar)', nuevas[-1]['op'] == 'update' and nuevas[-1]['data']['estado'] == 'ELIMINADO'
              and nuevas[-1]['data']['isDeleted'] is True and not any(w['op'] == 'delete' for w in escrituras(page)), nuevas[-1])

        tab(page, 'problematicas')
        page.click('.kcard[data-id=p1] .kcard-expand-btn')
        page.wait_for_timeout(200)
        check('Ninguna carga XSS se ejecutó en ninguna vista', page.evaluate('window.__T.xss') == 0, page.evaluate('window.__T.xss'))
        check('Ningún dato de otro contrato llega a la página', 'SECRETO' not in page.evaluate('document.body.innerHTML'))
        check('El IF no ve insignias de verificación', page.locator('.vbadge').count() == 0)
        check('Sin errores de JavaScript', not errores, errores)
    finally:
        browser.close()


def escenario_validador(p):
    print('\nB. Jefe de Departamento / Validador (Editor, contrato c1)')
    seed = base()
    s1 = {'tipo': 'avance', 'contratoId': 'c1', 'unidadId': 'u1', 'valorPropuesto': 70, 'valorVigente': 62, 'fechaReporte': d(-1),
          'nota': 'Pavimentos ' + XSS, 'estado': 'PENDIENTE_APROBACION', 'autorId': 'u_if1', 'creadoTs': 1790000000001, 'enviadoTs': 1790000000001}
    seed['solicitudes/s1'] = s1
    seed['audit/u_if1/eventos/solicitud-s1-crear'] = {'hash': sha(canon(['solicitud', 'avance', 'c1', 'u1', 70, s1['fechaReporte'], s1['nota'], 'u_if1', 1790000000001]))}
    seed['solicitudes/s2'] = {'tipo': 'fecha_programada', 'contratoId': 'c1', 'hitoId': 'h2', 'valorPropuesto': d(45), 'nota': 'Permisos',
                              'estado': 'PENDIENTE_APROBACION', 'autorId': 'u_if1', 'creadoTs': 1790000000002, 'enviadoTs': 1790000000002}
    seed['solicitudes/s3'] = {'tipo': 'fecha_real', 'contratoId': 'c1', 'hitoId': 'h3', 'valorPropuesto': d(-1), 'estado': 'PENDIENTE_APROBACION',
                              'autorId': 'u_val', 'creadoTs': 1790000000003, 'enviadoTs': 1790000000003}
    seed['problematicas/p1'] = {'contratoId': 'c1', 'unidadId': 'u1', 'titulo': 'Toma de terreno', 'descripcion': 'x', 'estado': 'escalado',
                                'nivelRiesgo': 'Extremo', 'escalamiento': ['Directora'], 'ts': 5, 'autorId': 'u_if1'}
    browser, page, errores = abrir(p, {'uid': 'u_val', 'name': 'Valentina Jefa', 'level': 'admin', 'seed': seed})
    try:
        ingresar(page)
        check('Badge con pendientes en la pestaña Bandeja', page.inner_text('#tabsNav [data-tab=bandeja] .tab-badge') == '3')
        tab(page, 'bandeja')
        page.wait_for_function("document.querySelector('#bjLista .sol[data-id=s1] .vbadge') && !document.querySelector('#bjLista .sol[data-id=s1] .vbadge').textContent.includes('verificando')", timeout=10000)
        card = page.inner_text('#bjLista .sol[data-id=s1]')
        check('Comparativo valor actual vs propuesto con diferencia', '62%' in card and '70%' in card and '+8 puntos porcentuales' in card, card)
        check('Autoría de la solicitud verificada por recibo', '✓ verificado' in card, card)
        check('Solicitud propia del validador no se puede aprobar', page.locator('#bjLista .sol[data-id=s3] .js-aprobar').count() == 0)
        check('Solicitudes de otros contratos no aparecen', page.locator('#bjLista .sol[data-id=sx]').count() == 0)

        n = len(escrituras(page))
        page.click('#bjLista .sol[data-id=s1] .js-aprobar')
        nuevas = esperar(page, 'solicitudes/s1', n)
        rutas = [w['path'] for w in nuevas]
        of = next(w for w in nuevas if w['path'] == 'oficial/avance-u1')['data']
        check('Aprobar publica el valor oficial, el historial y cierra la solicitud',
              of['valor'] == 70 and 'oficial/hist-s1' in rutas and nuevas[-1]['data']['estado'] == 'APROBADO', rutas)

        n = len(escrituras(page))
        page.click('#bjLista .sol[data-id=s2] .js-rechazar')
        page.click('#bjLista .sol[data-id=s2] .js-rechazo-ok')
        check('Rechazar sin comentario no se permite', 'obligatorio' in toast(page) and len(escrituras(page)) == n)
        page.fill('#bjLista .sol[data-id=s2] .bj-motivo', 'Falta respaldo del permiso sectorial')
        page.click('#bjLista .sol[data-id=s2] .js-rechazo-ok')
        nuevas = esperar(page, 'solicitudes/s2', n)
        check('Rechazo guardado con comentario', nuevas[-1]['data']['estado'] == 'RECHAZADO' and 'respaldo' in nuevas[-1]['data']['comentarioRevision'])

        n = len(escrituras(page))
        page.click('#bjAlertas .js-publicar[data-pid=p1]')
        nuevas = esperar(page, 'oficial/alerta-p1', n)
        check('Publicar alerta para Gabinete', nuevas[-1]['data']['isDeleted'] is False and nuevas[-1]['data']['nivelRiesgo'] == 'Extremo')
        n = len(escrituras(page))
        page.wait_for_selector('#bjAlertas .js-retirar[data-pid=p1]')
        page.click('#bjAlertas .js-retirar[data-pid=p1]')
        nuevas = esperar(page, 'oficial/alerta-p1', n)
        check('Retirar alerta = eliminación lógica', nuevas[-1]['op'] == 'set' and nuevas[-1]['data']['isDeleted'] is True)

        check('Selector "Ver como" visible para Editores', page.is_visible('#verComoWrap'))
        nq = len(page.evaluate('window.__T.queries'))
        page.select_option('#verComo', 'gabinete')
        page.wait_for_timeout(500)
        cols = [q['col'] for q in page.evaluate('window.__T.queries')[nq:]]
        check('Vista previa Gabinete solo consulta colecciones oficiales', sorted(cols) == ['hitos', 'oficial', 'unidades'], cols)
        check('Aviso de vista previa visible', 'Vista previa como Gabinete' in page.inner_text('#bannerTxt'))
        check('Ninguna carga XSS se ejecutó', page.evaluate('window.__T.xss') == 0)
        check('Sin errores de JavaScript', not errores, errores)
    finally:
        browser.close()


def escenario_gabinete(p):
    print('\nC. Gabinete (Lector: solo datos aprobados)')
    seed = base()
    seed['solicitudes/sp'] = {'tipo': 'avance', 'contratoId': 'c1', 'unidadId': 'u1', 'valorPropuesto': 99, 'estado': 'PENDIENTE_APROBACION',
                              'nota': 'NO-APROBADO', 'autorId': 'u_if1', 'creadoTs': 1790000000009, 'enviadoTs': 1790000000009}
    browser, page, errores = abrir(p, {'uid': 'u_gab', 'name': 'Gabinete DG', 'level': 'view', 'seed': seed})
    try:
        page.wait_for_selector('#gatePerfil', state='visible', timeout=15000)
        check('Lector entra automáticamente como Gabinete', 'Gabinete' in page.inner_text('#gatePerfilBox'))
        ingresar(page)
        cols = sorted(q['col'] for q in page.evaluate('window.__T.queries'))
        check('Gabinete solo consulta colecciones oficiales', cols == ['contratos', 'hitos', 'oficial', 'unidades'], cols)
        cuerpo = page.inner_text('#panel-gabinete')
        check('Muestra el avance aprobado (62%) y no la propuesta pendiente (99%)', '62%' in cuerpo and '99%' not in cuerpo and 'NO-APROBADO' not in cuerpo)
        check('Lista la alerta publicada y no la retirada', 'Alerta publicada' in cuerpo and 'ALERTA-RETIRADA' not in cuerpo)
        check('Semáforo rojo por alerta extrema', page.inner_text('.ccard[data-cid=c1] .sem') == 'Rojo')
        check('Sin formularios ni botones de edición', page.locator('#panel-gabinete input, #panel-gabinete textarea, #panel-gabinete .js-aprobar').count() == 0)
        check('Una sola pestaña y sin selector de perfil', page.locator('#tabsNav .tabd').count() == 1 and page.is_hidden('#verComoWrap'))
        check('Ninguna carga XSS se ejecutó', page.evaluate('window.__T.xss') == 0)
        check('Sin errores de JavaScript', not errores, errores)
    finally:
        browser.close()


def escenario_admin(p):
    print('\nD. Administrador del sistema (Editor sin perfil explícito)')
    browser, page, errores = abrir(p, {'uid': 'u_admin', 'name': 'Admin Central', 'level': 'admin', 'seed': base()})
    try:
        ingresar(page)
        tab(page, 'permisos')
        page.click('#permBuscar')
        page.fill('#permBuscar', 'Ana')
        page.wait_for_selector('#permResultados .js-elegir[data-uid=u_if2]')
        page.click('#permResultados .js-elegir[data-uid=u_if2]')
        page.wait_for_selector('#permTabla tr[data-uid=u_if2]')
        n = len(escrituras(page))
        page.click('#permTabla tr[data-uid=u_if2] .js-guardar-perm')
        check('Perfil IF sin contratos no se guarda', 'al menos un contrato' in toast(page) and len(escrituras(page)) == n)
        page.click('#permTabla tr[data-uid=u_if2] .perm-chip[data-cid=c2]')
        page.click('#permTabla tr[data-uid=u_if2] .js-guardar-perm')
        nuevas = esperar(page, 'permisos/u_if2', n)
        dd = nuevas[-1]['data']
        check('Permiso guardado con multiselección de contratos', dd['rol'] == 'if' and dd['contratos'] == ['c2'] and dd['activo'] is True, dd)
        check('Solo se guarda el id de la persona, no su nombre', 'Ana' not in json.dumps(dd))

        tab(page, 'config')
        n = len(escrituras(page))
        page.click('#cfHitos tr[data-id=h3] .js-hito-del')
        page.click('#cfHitos tr[data-id=h3] .js-hito-del-si')
        nuevas = esperar(page, 'hitos/h3', n)
        check('Eliminar hito = marca isDeleted (no borra)', nuevas[-1]['op'] == 'set' and nuevas[-1]['data']['isDeleted'] is True)
        check('Sin errores de JavaScript', not errores, errores)
    finally:
        browser.close()


def escenario_sin_perfil(p):
    print('\nE. Colaborador sin perfil asignado')
    browser, page, errores = abrir(p, {'uid': 'u_nuevo', 'name': 'Persona Nueva', 'level': 'interact', 'seed': base()})
    try:
        page.wait_for_selector('#gateFatal', state='visible', timeout=15000)
        check('Explica que no tiene perfil y no lo deja entrar', 'no tiene un perfil' in page.inner_text('#gateFatal') and page.is_hidden('#gateBtn'))
        check('Sin errores de JavaScript', not errores, errores)
    finally:
        browser.close()


def escenario_local(p):
    print('\nF. Modo local (HTML abierto como archivo, sin claude.ai)')
    tmp = AQUI / '_tmp_prueba.html'
    tmp.write_text('<script>window.__T = { xss: 0 };</script>\n' + PAGINA, encoding='utf-8')
    browser = p.chromium.launch(executable_path=CHROME, headless=True)
    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    errores = []
    page.on('pageerror', lambda e: errores.append(str(e)))
    try:
        page.goto(tmp.as_uri())
        page.wait_for_selector('#gatePerfil', state='visible', timeout=15000)
        check('Sin claude.ai arranca en modo local', 'Modo local' in page.inner_text('#gatePerfilBox'))
        page.select_option('#gateRol', 'if')
        ingresar(page)
        check('Carga los datos de ejemplo (3 contratos)', page.locator('#ctCards .ccard').count() == 3)
        check('Botón para restablecer datos visible', page.is_visible('#btnRestablecer'))
        tab(page, 'cargar')
        page.select_option('#cgAvUnidad', 'uA2')
        page.fill('#cgAvPct', '55')
        page.click('#formAvance button[type=submit]')
        check('Solicitud enviada en modo local', 'Enviado a revisión' in toast(page))

        page.reload()
        page.wait_for_selector('#gatePerfil', state='visible', timeout=15000)
        page.select_option('#gateRol', 'if')
        ingresar(page)
        tab(page, 'solicitudes')
        check('Los datos persisten al recargar la página', '55%' in page.inner_text('#solLista'))

        page.select_option('#verComo', 'validador')
        page.wait_for_timeout(400)
        tab(page, 'bandeja')
        card = page.locator('#bjLista .sol', has_text='55%')
        card.locator('.js-aprobar').click()
        check('Aprobación en modo local', 'Aprobada' in toast(page))
        page.select_option('#verComo', 'gabinete')
        page.wait_for_timeout(500)
        av = page.inner_text('#panel-gabinete .ccard[data-cid=dA] .av-num')
        check('Gabinete ve el nuevo promedio oficial (68% y 55% → 62%)', av == '62%', av)

        page.click('#btnRestablecer')
        page.click('#btnRestablecer')
        page.wait_for_timeout(500)
        av = page.inner_text('#panel-gabinete .ccard[data-cid=dA] .av-num')
        check('Restablecer vuelve a los datos de ejemplo (68% y 41% → 55%)', av == '55%', av)
        check('Ninguna carga XSS y sin errores de JavaScript', page.evaluate('window.__T.xss') == 0 and not errores, errores)
    finally:
        browser.close()


if __name__ == '__main__':
    with sync_playwright() as p:
        escenario_if(p)
        escenario_validador(p)
        escenario_gabinete(p)
        escenario_admin(p)
        escenario_sin_perfil(p)
        escenario_local(p)
    (AQUI / '_tmp_prueba.html').unlink(missing_ok=True)
    fallas = [r for r in resultados if not r[1]]
    print(f'\n{len(resultados) - len(fallas)}/{len(resultados)} pruebas OK')
    sys.exit(1 if fallas else 0)
