/*
 * Padrão único dos gráficos do sistema (Plotly), pensado para quem não é da área:
 * - dinheiro sempre em R$ no formato brasileiro (1.234,56);
 * - cores com papel fixo e seguras para daltonismo (validadas):
 *     entrou = azul, saiu = laranja, sobrou = azul, faltou = vermelho;
 *   nunca a cor sozinha: o sinal (+/−) e o nome vêm escritos junto;
 * - grade discreta, sem zoom/arrastar acidental, legenda em cima;
 * - cada gráfico tem uma frase-resumo e um estado "sem dados" que explica o que fazer.
 */
window.GF = (function () {
    'use strict';

    var COR = {
        entrou: '#2a78d6',
        saiu: '#eb6834',
        sobrou: '#2a78d6',
        faltou: '#e34948',
        saldo: '#2a78d6',
        ranking: '#2a78d6',
        bom: '#0ca30c',
        atencao: '#fab219',
        critico: '#d03b3b',
        textoBom: '#006300',
        textoRuim: '#b42318',
        tinta: '#0b0b0b',
        tinta2: '#52514e',
        apagado: '#898781',
        grade: '#e1e0d9',
        eixo: '#c3c2b7',
        superficie: '#ffffff'
    };

    var MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho',
                 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
    var MESES_CURTOS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

    var fmt2 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    var fmt0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });

    function num(v) { v = Number(v); return isFinite(v) ? v : 0; }

    /** R$ 1.234,56 · negativo como −R$ 1.234,56 */
    function brl(v, semCentavos) {
        v = num(v);
        var f = semCentavos ? fmt0 : fmt2;
        return (v < 0 ? '−' : '') + 'R$\u00a0' + f.format(Math.abs(v));
    }

    /** +R$ 1.234 / −R$ 1.234 (para "sobrou/faltou") */
    function comSinal(v, semCentavos) {
        v = num(v);
        return (v > 0 ? '+' : v < 0 ? '−' : '') + 'R$\u00a0' + (semCentavos ? fmt0 : fmt2).format(Math.abs(v));
    }

    /** R$ 1,2 mil · R$ 12 mil · R$ 1,3 mi (rótulos curtos dentro do gráfico) */
    function curto(v) {
        v = num(v);
        var a = Math.abs(v), s = v < 0 ? '−' : '';
        if (a >= 1e6) return s + 'R$\u00a0' + (a / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mi';
        if (a >= 1e4) return s + 'R$\u00a0' + fmt0.format(a / 1e3) + ' mil';
        if (a >= 1e3) return s + 'R$\u00a0' + (a / 1e3).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mil';
        return s + 'R$\u00a0' + fmt0.format(a);
    }

    function pct(v, casas) {
        return num(v).toLocaleString('pt-BR', { maximumFractionDigits: casas === undefined ? 0 : casas }) + '%';
    }

    function esc(s) {
        if (s === null || s === undefined) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function mesNome(i) { return MESES[i]; }          // i: 0..11
    function mesCurto(i) { return MESES_CURTOS[i]; }

    function mesclar(base, extra) {
        var out = Array.isArray(base) ? base.slice() : Object.assign({}, base);
        Object.keys(extra || {}).forEach(function (k) {
            var v = extra[k];
            out[k] = (v && typeof v === 'object' && !Array.isArray(v) && base && typeof base[k] === 'object' && !Array.isArray(base[k]))
                ? mesclar(base[k], v) : v;
        });
        return out;
    }

    function layout(extra) {
        var base = {
            font: { family: 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif', size: 13, color: COR.tinta2 },
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            separators: ',.',
            margin: { l: 16, r: 16, t: 8, b: 8 },
            hovermode: 'closest',
            hoverlabel: { bgcolor: '#ffffff', bordercolor: COR.grade, font: { color: COR.tinta, size: 13 }, align: 'left' },
            showlegend: false,
            legend: { orientation: 'h', x: 0, xanchor: 'left', y: 1.02, yanchor: 'bottom', font: { color: COR.tinta, size: 13 } },
            xaxis: { showgrid: false, zeroline: false, linecolor: COR.eixo, tickcolor: COR.eixo, ticks: '', fixedrange: true, automargin: true,
                     tickfont: { color: COR.tinta2 } },
            yaxis: { gridcolor: COR.grade, zeroline: true, zerolinecolor: COR.eixo, zerolinewidth: 1, linecolor: COR.eixo,
                     tickprefix: 'R$ ', tickformat: ',.0f', fixedrange: true, automargin: true, tickfont: { color: COR.apagado } },
            bargap: 0.35,
            bargroupgap: 0.12
        };
        return mesclar(base, extra || {});
    }

    var CONFIG = { responsive: true, displayModeBar: false, locale: 'pt-BR', scrollZoom: false, doubleClick: false };

    function desenhar(id, traces, extraLayout) {
        var el = typeof id === 'string' ? document.getElementById(id) : id;
        if (!el) return;
        el.innerHTML = '';
        if (!window.Plotly) {
            vazio(el, 'Não foi possível carregar o gráfico.', 'Recarregue a página.');
            return;
        }
        var lay = layout(extraLayout);
        // tela estreita (celular): rótulos do eixo X retos e espaçados, nada inclinado
        if (el.clientWidth && el.clientWidth < 640 && lay.xaxis.type === 'date') {
            lay.xaxis.tickangle = 0;
            lay.xaxis.nticks = 4;
        }
        if (el.clientWidth && el.clientWidth < 640 && lay.xaxis.visible !== false && lay.xaxis.type !== 'date') {
            var horizontal = traces.some(function (t) { return t.orientation === 'h'; });
            if (!horizontal) {
                lay.xaxis.tickangle = 0;
                var n = 0;
                traces.forEach(function (t) { if (t.x && t.x.length > n) n = t.x.length; });
                var cabem = Math.max(3, Math.floor(el.clientWidth / 64));
                if (n > cabem && traces[0].x && typeof traces[0].x[0] === 'string') {
                    var passo = Math.ceil(n / cabem), xs = traces[0].x;
                    lay.xaxis.tickmode = 'array';
                    lay.xaxis.tickvals = xs.filter(function (_, i) { return i % passo === 0; });
                    lay.xaxis.ticktext = lay.xaxis.tickvals;
                }
            }
        }
        Plotly.newPlot(el, traces, lay, CONFIG);
    }

    /** Estado sem dados: diz o que aconteceu e o que fazer. */
    function vazio(id, titulo, dica) {
        var el = typeof id === 'string' ? document.getElementById(id) : id;
        if (!el) return;
        if (window.Plotly && el.data) { try { Plotly.purge(el); } catch (e) { /* ignore */ } }
        el.innerHTML = '<div class="gf-vazio"><i class="bi bi-bar-chart" aria-hidden="true"></i>' +
            '<div class="gf-vazio-titulo">' + esc(titulo) + '</div>' +
            (dica ? '<div class="gf-vazio-dica">' + esc(dica) + '</div>' : '') + '</div>';
    }

    /** Frase-resumo acima do gráfico. `html` já deve vir escapado (use GF.esc nos textos do usuário). */
    function frase(id, html, tom) {
        var el = typeof id === 'string' ? document.getElementById(id) : id;
        if (!el) return;
        el.className = 'gf-frase' + (tom ? ' gf-frase-' + tom : '');
        el.innerHTML = html;
    }

    function erro(id) {
        vazio(id, 'Não foi possível carregar estes dados agora.', 'Tente recarregar a página.');
    }

    /** Barra horizontal de progresso acessível (HTML), para orçamentos, metas e cartões. */
    function barraProgresso(percentual, cor, rotulo) {
        var p = Math.max(0, Math.min(100, num(percentual)));
        return '<div class="gf-barra" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' +
            Math.round(p) + '" aria-label="' + esc(rotulo || '') + '">' +
            '<div class="gf-barra-preenchida" style="width:' + p + '%;background:' + cor + '"></div></div>';
    }

    /** Selo de situação: sempre ícone + texto, nunca só a cor. */
    function selo(tipo, texto) {
        var icones = { bom: 'bi-check-circle-fill', atencao: 'bi-exclamation-circle-fill', critico: 'bi-x-circle-fill', neutro: 'bi-dash-circle' };
        return '<span class="gf-selo gf-selo-' + tipo + '"><i class="bi ' + (icones[tipo] || icones.neutro) +
            '" aria-hidden="true"></i> ' + esc(texto) + '</span>';
    }

    return {
        COR: COR, brl: brl, comSinal: comSinal, curto: curto, pct: pct, esc: esc,
        mesNome: mesNome, mesCurto: mesCurto, layout: layout, desenhar: desenhar,
        vazio: vazio, frase: frase, erro: erro, barraProgresso: barraProgresso, selo: selo
    };
})();
