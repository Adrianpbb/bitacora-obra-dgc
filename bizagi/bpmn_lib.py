"""Mini-librería para describir un proceso con carriles y emitir:
  - BPMN 2.0 con diagrama (.bpmn) importable en Bizagi Modeler (Archivo > Importar > BPMN)
  - SVG del mismo diagrama (para revisar y para usar como imagen)

Cada elemento se ubica por (carril, columna); el enrutado de flechas es ortogonal.
"""
import html
import textwrap

LANE_H = 150
POOL_HDR = 30
LANE_HDR = 30
X0 = 20 + POOL_HDR + LANE_HDR          # inicio del área de contenido
COL_W = 190
TASK_W, TASK_H = 150, 84
GW = 50
EV = 36


def esc(s):
    return html.escape(str(s), quote=True)


class Node:
    def __init__(self, id, kind, label, lane, col, dy=0, doc='', label_pos='below'):
        self.id, self.kind, self.label, self.lane, self.col, self.dy = id, kind, label, lane, col, dy
        self.doc, self.label_pos = doc, label_pos
        if kind in ('user', 'service'):
            self.w, self.h = TASK_W, TASK_H
        elif kind in ('xor', 'and'):
            self.w = self.h = GW
        elif kind in ('start', 'end'):
            self.w = self.h = EV
        elif kind == 'note':
            self.w, self.h = 200, 64
        else:
            raise ValueError(kind)
        self.x = self.y = 0

    @property
    def cx(self): return self.x + self.w / 2
    @property
    def cy(self): return self.y + self.h / 2
    @property
    def r(self): return self.x + self.w
    @property
    def b(self): return self.y + self.h

    def port(self, p):
        return {'r': (self.r, self.cy), 'l': (self.x, self.cy),
                't': (self.cx, self.y), 'b': (self.cx, self.b)}[p]


class Flow:
    def __init__(self, id, src, tgt, label='', mode='auto', ports=None, via=None, mx=None, ly=None, lab_off=None):
        self.id, self.src, self.tgt, self.label = id, src, tgt, label
        self.mode, self.ports, self.via, self.mx, self.ly, self.lab_off = mode, ports, via, mx, ly, lab_off
        self.pts = []


class Process:
    def __init__(self, id, name, lanes, doc=''):
        self.id, self.name, self.lanes, self.doc = id, name, lanes, doc
        self.nodes, self.flows, self.notes = [], [], []
        self._n = 0

    # ---- construcción ----
    def add(self, id, kind, label, lane, col, **kw):
        n = Node(id, kind, label, self.lanes.index(lane), col, **kw)
        self._place(n)
        self.nodes.append(n)
        return n

    def _place(self, n):
        top = 20 + n.lane * LANE_H
        n.x = X0 + 30 + n.col * COL_W - n.w / 2 + (TASK_W / 2)
        n.y = top + LANE_H / 2 - n.h / 2 + n.dy

    def flow(self, src, tgt, label='', **kw):
        self._n += 1
        f = Flow('F%02d' % self._n, src, tgt, label, **kw)
        self.flows.append(f)
        return f

    def note(self, id, text, lane, col, attach, dy=0):
        n = Node(id, 'note', text, self.lanes.index(lane), col, dy=dy)
        self._place(n)
        self.nodes.append(n)
        self.notes.append((n, attach))
        return n

    def byid(self, id):
        for n in self.nodes:
            if n.id == id:
                return n
        raise KeyError(id)

    # ---- layout ----
    def layout(self):
        maxcol = max(n.r for n in self.nodes)
        self.width = maxcol + 60
        self.height = 40 + len(self.lanes) * LANE_H
        for f in self.flows:
            self._route(f)

    def _route(self, f):
        s, t = self.byid(f.src), self.byid(f.tgt)
        m = f.mode
        if f.via is not None:                      # puntos intermedios absolutos
            p1, p2 = f.ports or ('r', 'l')
            f.pts = [s.port(p1)] + list(f.via) + [t.port(p2)]
            return
        if m == 'auto':
            if abs(s.cy - t.cy) < 1 and t.x > s.r:
                m = 'h'
            elif t.x > s.r:
                m = 'hvh'
            elif abs(s.cx - t.cx) < 1:
                m = 'v'
            else:
                m = 'loop'
        if m == 'h':
            f.pts = [s.port('r'), t.port('l')]
        elif m == 'v':
            if t.cy > s.cy:
                f.pts = [s.port('b'), t.port('t')]
            else:
                f.pts = [s.port('t'), t.port('b')]
        elif m == 'hvh':
            a, b = s.port('r'), t.port('l')
            mx = f.mx if f.mx is not None else (a[0] + b[0]) / 2
            f.pts = [a, (mx, a[1]), (mx, b[1]), b]
        elif m == 'hv':                            # horizontal y luego vertical al borde del destino
            a = s.port('r')
            if t.cy > s.cy:
                b = t.port('t')
            else:
                b = t.port('b')
            f.pts = [a, (b[0], a[1]), b]
        elif m == 'vh':                            # vertical y luego horizontal a la izquierda del destino
            a = s.port('b') if t.cy > s.cy else s.port('t')
            b = t.port('l')
            f.pts = [a, (a[0], b[1]), b]
        elif m == 'vhv':                           # vertical, horizontal, vertical
            a = s.port('b') if t.cy > s.cy else s.port('t')
            b = t.port('t') if t.cy > s.cy else t.port('b')
            my = f.ly if f.ly is not None else (a[1] + b[1]) / 2
            f.pts = [a, (a[0], my), (b[0], my), b]
        elif m in ('loop', 'looptop'):             # retorno hacia atrás por debajo / por arriba
            if m == 'loop':
                a, b = s.port('b'), t.port('b')
                y = f.ly if f.ly is not None else max(s.b, t.b) + 28
            else:
                a, b = s.port('t'), t.port('t')
                y = f.ly if f.ly is not None else min(s.y, t.y) - 28
            f.pts = [a, (a[0], y), (b[0], y), b]
        else:
            raise ValueError(m)

    # ---- BPMN ----
    def to_bpmn(self):
        self.layout()
        tag = {'user': 'userTask', 'service': 'serviceTask', 'xor': 'exclusiveGateway',
               'and': 'parallelGateway', 'start': 'startEvent', 'end': 'endEvent'}
        flownodes = [n for n in self.nodes if n.kind != 'note']
        out_f = {n.id: [] for n in flownodes}
        in_f = {n.id: [] for n in flownodes}
        for f in self.flows:
            out_f[f.src].append(f.id)
            in_f[f.tgt].append(f.id)
        L = []
        L.append('<?xml version="1.0" encoding="UTF-8"?>')
        L.append('<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
                 'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
                 'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
                 'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
                 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                 'id="Defs_%s" targetNamespace="http://dgc.mop.cl/bitacora-obra" '
                 'exporter="Bitacora de Obra DGC" exporterVersion="1.0">' % self.id)
        L.append('  <bpmn:collaboration id="Collab_%s">' % self.id)
        L.append('    <bpmn:participant id="Pool_%s" name="%s" processRef="Proc_%s" />' % (self.id, esc(self.name), self.id))
        L.append('  </bpmn:collaboration>')
        L.append('  <bpmn:process id="Proc_%s" name="%s" isExecutable="false">' % (self.id, esc(self.name)))
        if self.doc:
            L.append('    <bpmn:documentation>%s</bpmn:documentation>' % esc(self.doc))
        L.append('    <bpmn:laneSet id="LaneSet_%s">' % self.id)
        for i, ln in enumerate(self.lanes):
            L.append('      <bpmn:lane id="Lane_%s_%d" name="%s">' % (self.id, i, esc(ln)))
            for n in flownodes:
                if n.lane == i:
                    L.append('        <bpmn:flowNodeRef>%s</bpmn:flowNodeRef>' % n.id)
            L.append('      </bpmn:lane>')
        L.append('    </bpmn:laneSet>')
        for n in flownodes:
            nm = ' name="%s"' % esc(n.label) if n.label and n.kind not in ('xor', 'and') or (n.kind in ('xor', 'and') and n.label) else ''
            body = []
            if n.doc:
                body.append('      <bpmn:documentation>%s</bpmn:documentation>' % esc(n.doc))
            for fid in in_f[n.id]:
                body.append('      <bpmn:incoming>%s</bpmn:incoming>' % fid)
            for fid in out_f[n.id]:
                body.append('      <bpmn:outgoing>%s</bpmn:outgoing>' % fid)
            extra = ''
            if n.kind == 'xor':
                extra = ' gatewayDirection="Diverging"' if len(out_f[n.id]) > 1 else ' gatewayDirection="Converging"'
            L.append('    <bpmn:%s id="%s"%s%s>' % (tag[n.kind], n.id, nm, extra))
            L.extend(body)
            L.append('    </bpmn:%s>' % tag[n.kind])
        for f in self.flows:
            nm = ' name="%s"' % esc(f.label) if f.label else ''
            L.append('    <bpmn:sequenceFlow id="%s"%s sourceRef="%s" targetRef="%s" />' % (f.id, nm, f.src, f.tgt))
        for n, att in self.notes:
            L.append('    <bpmn:textAnnotation id="%s"><bpmn:text>%s</bpmn:text></bpmn:textAnnotation>' % (n.id, esc(n.label)))
            L.append('    <bpmn:association id="As_%s" sourceRef="%s" targetRef="%s" />' % (n.id, att, n.id))
        L.append('  </bpmn:process>')
        L.append('  <bpmndi:BPMNDiagram id="Diag_%s">' % self.id)
        L.append('    <bpmndi:BPMNPlane id="Plane_%s" bpmnElement="Collab_%s">' % (self.id, self.id))
        L.append('      <bpmndi:BPMNShape id="Sh_Pool" bpmnElement="Pool_%s" isHorizontal="true">'
                 '<dc:Bounds x="20" y="20" width="%d" height="%d" /></bpmndi:BPMNShape>' % (
                     self.id, self.width - 20, len(self.lanes) * LANE_H))
        for i, ln in enumerate(self.lanes):
            L.append('      <bpmndi:BPMNShape id="Sh_Lane%d" bpmnElement="Lane_%s_%d" isHorizontal="true">'
                     '<dc:Bounds x="%d" y="%d" width="%d" height="%d" /></bpmndi:BPMNShape>' % (
                         i, self.id, i, 20 + POOL_HDR, 20 + i * LANE_H, self.width - 20 - POOL_HDR, LANE_H))
        for n in self.nodes:
            extra = ''
            if n.kind == 'xor':
                extra = ' isMarkerVisible="true"'
            lab = ''
            if n.kind in ('start', 'end') and n.label:
                lab = '<bpmndi:BPMNLabel><dc:Bounds x="%d" y="%d" width="110" height="40" /></bpmndi:BPMNLabel>' % (
                    n.cx - 55, n.b + 4)
            elif n.kind in ('xor', 'and') and n.label:
                lx, ly = self._gw_label_xy(n)
                lab = '<bpmndi:BPMNLabel><dc:Bounds x="%d" y="%d" width="120" height="44" /></bpmndi:BPMNLabel>' % (lx, ly)
            L.append('      <bpmndi:BPMNShape id="Sh_%s" bpmnElement="%s"%s><dc:Bounds x="%d" y="%d" width="%d" height="%d" />%s</bpmndi:BPMNShape>' % (
                n.id, n.id, extra, n.x, n.y, n.w, n.h, lab))
        for f in self.flows:
            L.append('      <bpmndi:BPMNEdge id="Ed_%s" bpmnElement="%s">' % (f.id, f.id))
            for (x, y) in f.pts:
                L.append('        <di:waypoint x="%d" y="%d" />' % (x, y))
            if f.label:
                lx, ly = self._flow_label_xy(f)
                L.append('        <bpmndi:BPMNLabel><dc:Bounds x="%d" y="%d" width="%d" height="16" /></bpmndi:BPMNLabel>' % (
                    lx, ly, 8 * len(f.label) * 0.7 + 8))
            L.append('      </bpmndi:BPMNEdge>')
        for n, att in self.notes:
            a = self.byid(att)
            p1 = self._near(n, a)
            p2 = self._near(a, n)
            L.append('      <bpmndi:BPMNEdge id="Ed_As_%s" bpmnElement="As_%s"><di:waypoint x="%d" y="%d" /><di:waypoint x="%d" y="%d" /></bpmndi:BPMNEdge>' % (
                n.id, n.id, p1[0], p1[1], p2[0], p2[1]))
        L.append('    </bpmndi:BPMNPlane>')
        L.append('  </bpmndi:BPMNDiagram>')
        L.append('</bpmn:definitions>')
        return '\n'.join(L) + '\n'

    def _gw_label_xy(self, n):
        if n.label_pos == 'above':
            return n.cx - 60, n.y - 48
        return n.cx - 60, n.b + 2

    def _flow_label_xy(self, f):
        if f.lab_off:
            return f.pts[0][0] + f.lab_off[0], f.pts[0][1] + f.lab_off[1]
        if f.label and f.mode in ('loop', 'looptop') and len(f.pts) == 4:
            return (f.pts[1][0] + f.pts[2][0]) / 2 - 60, f.pts[1][1] + (-4 if f.mode == 'looptop' else 4)
        (x1, y1), (x2, y2) = f.pts[0], f.pts[1]
        if len(f.pts) == 4 and abs(x2 - x1) < 80 and abs(y1 - y2) < 1:   # salida corta de compuerta: al lado de la vertical
            y3 = f.pts[2][1]
            return x2 + 4, (y2 - 36 if y3 < y2 else y2 + 6)
        if abs(y1 - y2) < 1:                       # tramo horizontal: etiqueta arriba
            return min(x1, x2) + 6, y1 - 18
        return x1 + 6, (y1 + y2) / 2 - 8           # tramo vertical: etiqueta al costado

    def _near(self, a, b):
        if b.cx > a.r:
            return a.port('r')
        if b.cx < a.x:
            return a.port('l')
        return a.port('b') if b.cy > a.cy else a.port('t')

    # ---- SVG ----
    def to_svg(self):
        self.layout()
        W, H = self.width + 20, self.height + 20
        S = []
        S.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" font-family="Arial, Helvetica, sans-serif">' % (W, H, W, H))
        S.append('<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
                 '<path d="M0,0 L10,5 L0,10 z" fill="#1f3a5f"/></marker></defs>')
        S.append('<rect width="100%" height="100%" fill="#ffffff"/>')
        S.append('<rect x="20" y="20" width="%d" height="%d" fill="#fff" stroke="#1f3a5f" stroke-width="1.5"/>' % (self.width - 20, len(self.lanes) * LANE_H))
        S.append('<rect x="20" y="20" width="%d" height="%d" fill="#1f3a5f"/>' % (POOL_HDR, len(self.lanes) * LANE_H))
        S.append('<text transform="translate(%d,%d) rotate(-90)" text-anchor="middle" fill="#fff" font-size="13" font-weight="bold">%s</text>' % (
            20 + POOL_HDR / 2 + 5, 20 + len(self.lanes) * LANE_H / 2, esc(self.name)))
        palette = ['#f4f8fd', '#ffffff']
        for i, ln in enumerate(self.lanes):
            y = 20 + i * LANE_H
            S.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" stroke="#1f3a5f" stroke-width="1"/>' % (
                20 + POOL_HDR, y, self.width - 20 - POOL_HDR, LANE_H, palette[i % 2]))
            S.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#dbe7f5" stroke="#1f3a5f" stroke-width="1"/>' % (
                20 + POOL_HDR, y, LANE_HDR, LANE_H))
            S.append('<text transform="translate(%d,%d) rotate(-90)" text-anchor="middle" fill="#1f3a5f" font-size="12" font-weight="bold">%s</text>' % (
                20 + POOL_HDR + LANE_HDR / 2 + 4, y + LANE_H / 2, esc(ln)))
        for f in self.flows:
            pts = ' '.join('%.0f,%.0f' % p for p in f.pts)
            S.append('<polyline points="%s" fill="none" stroke="#1f3a5f" stroke-width="1.6" marker-end="url(#ar)"/>' % pts)
            if f.label:
                lx, ly = self._flow_label_xy(f)
                S.append('<text x="%.0f" y="%.0f" font-size="11" fill="#b03a2e" font-weight="bold">%s</text>' % (lx, ly + 12, esc(f.label)))
        for n, att in self.notes:
            a = self.byid(att)
            p1, p2 = self._near(n, a), self._near(a, n)
            S.append('<line x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f" stroke="#888" stroke-dasharray="4 3"/>' % (p1[0], p1[1], p2[0], p2[1]))
        for n in self.nodes:
            S.append(self._svg_node(n))
        S.append('</svg>')
        return '\n'.join(S) + '\n'

    def _lines(self, text, width_chars):
        out = []
        for para in str(text).split('\n'):
            out.extend(textwrap.wrap(para, width_chars) or [''])
        return out

    def _svg_node(self, n):
        k = n.kind
        if k in ('user', 'service'):
            fill = '#e8f1fb' if k == 'user' else '#eef3ea'
            s = '<rect x="%.0f" y="%.0f" width="%d" height="%d" rx="8" fill="%s" stroke="#1f3a5f" stroke-width="1.6"/>' % (n.x, n.y, n.w, n.h, fill)
            mark = '☺' if k == 'user' else '⚙'
            s += '<text x="%.0f" y="%.0f" font-size="11" fill="#5b6b82">%s</text>' % (n.x + 6, n.y + 14, mark)
            lines = self._lines(n.label, 22)[:5]
            y0 = n.cy - (len(lines) - 1) * 6.5 + 3
            for i, ln in enumerate(lines):
                s += '<text x="%.0f" y="%.0f" font-size="11" text-anchor="middle" fill="#14233a">%s</text>' % (n.cx, y0 + i * 13, esc(ln))
            return s
        if k in ('xor', 'and'):
            pts = '%.0f,%.0f %.0f,%.0f %.0f,%.0f %.0f,%.0f' % (n.cx, n.y, n.r, n.cy, n.cx, n.b, n.x, n.cy)
            s = '<polygon points="%s" fill="#fff8e1" stroke="#1f3a5f" stroke-width="1.6"/>' % pts
            if k == 'xor':
                s += '<path d="M%.0f,%.0f L%.0f,%.0f M%.0f,%.0f L%.0f,%.0f" stroke="#1f3a5f" stroke-width="2.4"/>' % (
                    n.cx - 9, n.cy - 9, n.cx + 9, n.cy + 9, n.cx + 9, n.cy - 9, n.cx - 9, n.cy + 9)
            else:
                s += '<path d="M%.0f,%.0f L%.0f,%.0f M%.0f,%.0f L%.0f,%.0f" stroke="#1f3a5f" stroke-width="2.4"/>' % (
                    n.cx - 11, n.cy, n.cx + 11, n.cy, n.cx, n.cy - 11, n.cx, n.cy + 11)
            if n.label:
                lines = self._lines(n.label, 22)[:3]
                y = n.b + 14 if n.label_pos == 'below' else n.y - 6 - (len(lines) - 1) * 12
                for i, ln in enumerate(lines):
                    s += '<text x="%.0f" y="%.0f" font-size="11" text-anchor="middle" font-weight="bold" fill="#14233a">%s</text>' % (n.cx, y + i * 12, esc(ln))
            return s
        if k in ('start', 'end'):
            sw = 1.8 if k == 'start' else 4
            col = '#2e7d32' if k == 'start' else '#b03a2e'
            s = '<circle cx="%.0f" cy="%.0f" r="%d" fill="#fff" stroke="%s" stroke-width="%s"/>' % (n.cx, n.cy, n.w / 2 - 1, col, sw)
            if n.label:
                lines = self._lines(n.label, 22)[:3]
                for i, ln in enumerate(lines):
                    s += '<text x="%.0f" y="%.0f" font-size="11" text-anchor="middle" fill="#14233a">%s</text>' % (n.cx, n.b + 14 + i * 12, esc(ln))
            return s
        if k == 'note':
            s = '<path d="M%.0f,%.0f L%.0f,%.0f L%.0f,%.0f L%.0f,%.0f L%.0f,%.0f Z" fill="#fffde7" stroke="#b8a600"/>' % (
                n.x + 14, n.y, n.r, n.y, n.r, n.b, n.x, n.b, n.x, n.y + 14)
            lines = self._lines(n.label, 34)[:4]
            for i, ln in enumerate(lines):
                s += '<text x="%.0f" y="%.0f" font-size="10" fill="#5d5400">%s</text>' % (n.x + 8, n.y + 22 + i * 12, esc(ln))
            return s
        return ''
