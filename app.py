from flask import Flask, render_template, request, redirect, session, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, io
from datetime import datetime, date, timedelta
import pandas as pd
import calendar
from collections import OrderedDict
from flask import g

app = Flask(__name__)
app.secret_key = "sua_chave_secreta_aqui"  # Lembre de alterar

# Filtro Jinja para trocar ponto por vírgula
def ponto_para_virgula(valor):
    return str(valor).replace('.', ',')

app.jinja_env.filters['ponto_virgula'] = ponto_para_virgula
app.secret_key = os.urandom(24)

def get_db_connection():
    conn = sqlite3.connect("banco.db")
    conn.row_factory = sqlite3.Row
    return conn

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect("banco.db")
        g.db.row_factory = sqlite3.Row
    return g.db


def criar_banco():
    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            banca_inicial REAL DEFAULT 0
        )
    ''')

    # Verifica e adiciona coluna se não existir (para bancos já criados)
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN banca_inicial REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Coluna já existe

    # Tabela de apostas continua igual
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS apostas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            data TEXT,
            metodo TEXT,
            casa TEXT,
            visitante TEXT,
            stake REAL,
            odd REAL,
            minuto_gol INTEGER,
            valor_realizado REAL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    ''')

    conn.commit()
    conn.close()

def conectar_banco():
    conn = sqlite3.connect('banco.db')  # Substitua pelo caminho do seu arquivo .db
    conn.row_factory = sqlite3.Row  # Para acessar as colunas pelo nome
    return conn

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nome = request.form["nome"]
        email = request.form["email"]
        senha = generate_password_hash(request.form["senha"])
        banca_inicial = float(request.form["banca_inicial"])

        conn = sqlite3.connect("banco.db")
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO usuarios (nome, email, senha, banca_inicial) VALUES (?, ?, ?, ?)",
                (nome, email, senha, banca_inicial)
            )
            conn.commit()
            return redirect("/login")
        except sqlite3.IntegrityError:
            return "Email já cadastrado"
        finally:
            conn.close()

    return render_template("register.html")



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        senha = request.form["senha"]

        conn = sqlite3.connect("banco.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
        usuario = cursor.fetchone()
        conn.close()

        if usuario and check_password_hash(usuario[3], senha):
            session["usuario_id"] = usuario[0]
            session["nome"] = usuario[1]
            return redirect("/perfil")
        else:
            return "Credenciais inválidas"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/", methods=["GET", "POST"])
def index():
    if "usuario_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        usuario_id = session["usuario_id"]
        data_input = request.form["data"]
        try:
            data_obj = datetime.strptime(data_input, "%Y-%m-%d")
            data_banco = data_obj.strftime("%Y-%m-%d")
        except ValueError:
            return "Data inválida. Use o seletor de data do navegador."

        dados = (
            usuario_id,
            data_banco,
            request.form["metodo"],
            request.form["casa"],
            request.form["visitante"],
            float(request.form["stake"]),
            float(request.form["odd"]),
            int(request.form["minuto_gol"]),
            float(request.form["valor_realizado"])
        )
        conn = sqlite3.connect("banco.db")
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO apostas (
                usuario_id, data, metodo, casa, visitante, stake, odd, minuto_gol, valor_realizado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', dados)
        conn.commit()
        conn.close()
        return redirect("/apostas")

    return render_template("index.html")


@app.route("/apostas")
def apostas():
    if "usuario_id" not in session:
        return redirect("/login")

    usuario_id = session["usuario_id"]
    data_inicio = request.args.get("data_inicio")
    data_fim = request.args.get("data_fim")
    metodo = request.args.get("metodo")

    query = "SELECT * FROM apostas WHERE usuario_id = ?"
    params = [usuario_id]
    if data_inicio:
        query += " AND data >= ?"
        params.append(data_inicio)
    if data_fim:
        query += " AND data <= ?"
        params.append(data_fim)
    if metodo:
        query += " AND metodo = ?"
        params.append(metodo)

    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    apostas = cursor.fetchall()
    conn.close()

    apostas_formatadas = []
    sequencial = 1
    for aposta in apostas:
        data_str = aposta[2]
        try:
            data_formatada = datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        except:
            data_formatada = data_str

        minuto_gol = aposta[8]
        if minuto_gol is None:
            minuto_gol = ''  # deixa vazio se não informado

        apostas_formatadas.append((
            aposta[0],      # id
            aposta[1],      # usuario_id
            data_formatada, # data
            aposta[3],      # metodo
            aposta[4],      # casa
            aposta[5],      # visitante
            aposta[6],      # stake
            aposta[7],      # odd
            minuto_gol,     # minuto_gol (trata None)
            aposta[9],      # valor_realizado
            sequencial      # número sequencial
        ))
        sequencial += 1


    total_apostas = len(apostas)
    total_stake = sum(float(a[6]) for a in apostas) if total_apostas > 0 else 0.0
    total_retorno = sum(float(a[9]) for a in apostas) if total_apostas > 0 else 0.0
    lucro = total_retorno - total_stake
    roi = (lucro / total_stake * 100) if total_stake > 0 else 0.0
    winrate = (sum(1 for a in apostas if float(a[9]) > float(a[6])) / total_apostas * 100) if total_apostas > 0 else 0.0

    def converte_para_iso(data):
        if not data:
            return ''
        try:
            datetime.strptime(data, "%Y-%m-%d")
            return data
        except:
            try:
                return datetime.strptime(data, "%d/%m/%Y").strftime("%Y-%m-%d")
            except:
                return ''

    data_inicio_iso = converte_para_iso(data_inicio)
    data_fim_iso = converte_para_iso(data_fim)

    return render_template(
        "apostas.html",
        apostas=apostas_formatadas,
        data_inicio_iso=data_inicio_iso,
        data_fim_iso=data_fim_iso,
        metodo=metodo or '',
        total_apostas=total_apostas,
        total_stake=total_stake,
        total_retorno=total_retorno,
        lucro=lucro,
        roi=roi,
        winrate=winrate
    )

@app.route("/apostas/excluir/<int:id>", methods=["POST"])
def excluir_aposta(id):
    if "usuario_id" not in session:
        return redirect("/login")

    usuario_id = session["usuario_id"]
    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM apostas WHERE id = ? AND usuario_id = ?", (id, usuario_id))
    conn.commit()
    conn.close()
    return redirect(url_for("apostas"))

@app.route("/apostas/editar/<int:id>", methods=["GET", "POST"])
def editar_aposta(id):
    if "usuario_id" not in session:
        return redirect("/login")

    usuario_id = session["usuario_id"]
    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.form["data"]
        metodo = request.form["metodo"]
        casa = request.form["casa"]
        visitante = request.form["visitante"]
        stake = float(request.form["stake"])
        odd = float(request.form["odd"])

        # Aqui trata o minuto_gol opcional, aceita vazio
        minuto_gol_raw = request.form.get("minuto_gol", "")
        minuto_gol = int(minuto_gol_raw) if minuto_gol_raw.strip().isdigit() else None

        valor_realizado = float(request.form["valor_realizado"])

        cursor.execute("""
            UPDATE apostas SET data=?, metodo=?, casa=?, visitante=?, stake=?, odd=?, minuto_gol=?, valor_realizado=?
            WHERE id=? AND usuario_id=?
        """, (data, metodo, casa, visitante, stake, odd, minuto_gol, valor_realizado, id, usuario_id))
        conn.commit()
        conn.close()
        return redirect(url_for("apostas"))

    cursor.execute("SELECT * FROM apostas WHERE id = ? AND usuario_id = ?", (id, usuario_id))
    aposta = cursor.fetchone()
    conn.close()

    if not aposta:
        return "Aposta não encontrada ou sem permissão.", 404

    try:
        data_iso = datetime.strptime(aposta[2], "%d/%m/%Y").strftime("%Y-%m-%d")
    except:
        data_iso = aposta[2]

    return render_template("editar_aposta.html", aposta=aposta, data_iso=data_iso)


@app.route("/apostas/exportar")
def exportar_apostas():
    if "usuario_id" not in session:
        return redirect("/login")

    usuario_id = session["usuario_id"]
    data_inicio = request.args.get("data_inicio")
    data_fim = request.args.get("data_fim")
    metodo = request.args.get("metodo")

    query = "SELECT id, data, metodo, casa, visitante, stake, odd, minuto_gol, valor_realizado FROM apostas WHERE usuario_id = ?"
    params = [usuario_id]
    if data_inicio:
        query += " AND data >= ?"
        params.append(data_inicio)
    if data_fim:
        query += " AND data <= ?"
        params.append(data_fim)
    if metodo:
        query += " AND metodo = ?"
        params.append(metodo)

    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    apostas = cursor.fetchall()
    conn.close()

    df = pd.DataFrame(apostas, columns=[
        "ID", "Data", "Método", "Casa", "Visitante",
        "Stake", "Odd", "Minuto Gol", "Valor Realizado"
    ])
    df["Data"] = pd.to_datetime(df["Data"]).dt.strftime("%d/%m/%Y")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Apostas")
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name="historico_apostas.xlsx",
        as_attachment=True
    )


@app.route("/estatisticas")
def estatisticas():
    if "usuario_id" not in session:
        return redirect("/login")

    usuario_id = session["usuario_id"]
    banca_inicial = 50.0  # ou pegue do banco

    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT data, stake, odd, valor_realizado
        FROM apostas
        WHERE usuario_id = ?
        ORDER BY data
    """, (usuario_id,))
    rows = cursor.fetchall()
    conn.close()

    daily = OrderedDict()
    for data_str, stake, odd, valor_realizado in rows:
        try:
            dia = datetime.strptime(data_str, "%Y-%m-%d").date()
        except:
            continue
        daily.setdefault(dia, []).append(float(valor_realizado))

    labels = []
    banca = []
    saldo = banca_inicial

    for dia, valores in daily.items():
        labels.append(dia.strftime("%d/%m/%Y"))
        saldo += sum(valores)
        banca.append(round(saldo, 2))

    return render_template("estatisticas.html",
                           labels=labels,
                           banca=banca,
                           banca_inicial=banca_inicial)


@app.route("/estatisticas_diarias")
def estatisticas_diarias():
    # Esta rota foi removida; não precisa existir. Se ainda existir no seu arquivo, delete-a.
    return redirect(url_for("calendario"))

@app.route("/calendario")
def calendario():
    if "usuario_id" not in session:
        return redirect("/login")

    usuario_id = session["usuario_id"]

    # Pega ano e mês do filtro ou usa data atual
    year = request.args.get("year", None, type=int)
    month = request.args.get("month", None, type=int)

    hoje = date.today()
    if not year:
        year = hoje.year
    if not month:
        month = hoje.month

    # Pega banca inicial do usuário (ajuste o nome do campo e tabela conforme seu DB)
    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()
    cursor.execute("SELECT banca_inicial FROM usuarios WHERE id = ?", (usuario_id,))
    row = cursor.fetchone()
    banca_inicial = row[0] if row else 50.0
    conn.close()

    # Busca apostas do mês/ano selecionados
    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT data, valor_realizado, stake FROM apostas
        WHERE usuario_id = ?
        AND strftime('%Y', data) = ?
        AND strftime('%m', data) = ?
    """, (usuario_id, str(year), f"{month:02d}"))
    rows = cursor.fetchall()
    conn.close()

    # Organiza apostas por dia em ordem cronológica
    daily = OrderedDict()
    for data_str, valor_realizado, stake in rows:
        try:
            dia = datetime.strptime(data_str, "%Y-%m-%d").date()
        except:
            continue
        daily.setdefault(dia, []).append({
            "valor_realizado": float(valor_realizado),
            "stake": float(stake)
        })

    banca_acumulada = banca_inicial
    daily_pct = {}

    for dia, apostas_list in daily.items():
        lucro_dia = sum(item["valor_realizado"] for item in apostas_list)
        if banca_acumulada <= 0:
            pct = 0
        else:
            pct = (lucro_dia / banca_acumulada) * 100
        daily_pct[dia] = round(pct, 2)
        banca_acumulada += lucro_dia

    # Construir a estrutura para o calendário (weeks e cells)
    cal = calendar.Calendar(firstweekday=6)  # domingo como primeiro dia
    calendar_weeks = []
    for week in cal.monthdatescalendar(year, month):
        week_data = []
        for day in week:
            if day.month == month:
                pct = daily_pct.get(day, None)  # pega percentual do dia ou None
                week_data.append({"day": day.day, "pct": pct})
            else:
                # Dias fora do mês
                week_data.append({"day": None, "pct": None})
        calendar_weeks.append(week_data)

    # Obter lista de anos disponíveis para filtro (opcional)
    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT strftime('%Y', data) FROM apostas WHERE usuario_id = ?", (usuario_id,))
    years_raw = cursor.fetchall()
    conn.close()
    available_years = sorted({int(y[0]) for y in years_raw if y[0] is not None})

    return render_template(
        "calendario.html",
        calendar_weeks=calendar_weeks,
        year=year,
        month=month,
        available_years=available_years
    )



@app.route("/estatisticas_diarias_completa")
def estatisticas_diarias_completa():
    if "usuario_id" not in session:
        return redirect("/login")

    usuario_id = session["usuario_id"]
    data_inicio = request.args.get("data_inicio")
    data_fim    = request.args.get("data_fim")
    metodo      = request.args.get("metodo")

    query = "SELECT data, stake, odd, valor_realizado FROM apostas WHERE usuario_id = ?"
    params = [usuario_id]
    if data_inicio:
        query += " AND data >= ?"
        params.append(data_inicio)
    if data_fim:
        query += " AND data <= ?"
        params.append(data_fim)
    if metodo:
        query += " AND metodo = ?"
        params.append(metodo)

    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    daily = OrderedDict()
    for data_str, stake, odd, valor_realizado in rows:
        try:
            dia = datetime.strptime(data_str, "%Y-%m-%d").date()
        except:
            continue
        daily.setdefault(dia, []).append({
            "stake": float(stake),
            "odd": float(odd),
            "valor_realizado": float(valor_realizado)
        })

    resultados = []
    banca_acumulada = 50.0

    for dia, apostas_list in daily.items():
        qtd_entradas = len(apostas_list)
        lucro_dia = sum(item["valor_realizado"]  for item in apostas_list)
        greens = sum(1 for item in apostas_list if item["valor_realizado"] > 0)
        reds = sum(1 for item in apostas_list if item["valor_realizado"] < 0)
        odd_media = (sum(item["odd"] for item in apostas_list) / qtd_entradas) if qtd_entradas > 0 else 0
        stake_media = (sum(item["stake"] for item in apostas_list) / qtd_entradas) if qtd_entradas > 0 else 0

        pct_lucro = 0.0 if banca_acumulada <= 0 else (lucro_dia / banca_acumulada) * 100

        banca_acumulada += lucro_dia

        resultados.append({
            "data": dia.strftime("%d/%m/%Y"),
            "lucro_dia": round(lucro_dia, 2),
            "pct_lucro": round(pct_lucro, 2),
            "qtd_entradas": qtd_entradas,
            "greens": greens,
            "reds": reds,
            "odd_media": round(odd_media, 2),
            "stake_media": round(stake_media, 2),
            "banca_acumulada": round(banca_acumulada, 2)
        })

    return render_template(
        "estatisticas_diarias_completa.html",
        resultados=resultados
    )


@app.route("/editar_banca", methods=["GET", "POST"])
def editar_banca():
    if "usuario_id" not in session:
        return redirect("/login")

    usuario_id = session["usuario_id"]
    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()

    if request.method == "POST":
        nova_banca = request.form.get("banca_inicial")
        mensagem = None
        try:
            nova_banca_float = float(nova_banca)
            if nova_banca_float < 0:
                mensagem = "Valor da banca não pode ser negativo."
            else:
                cursor.execute("UPDATE usuarios SET banca_inicial = ? WHERE id = ?", (nova_banca_float, usuario_id))
                conn.commit()
                mensagem = "Banca atualizada com sucesso!"
        except ValueError:
            mensagem = "Valor inválido para banca."
        finally:
            cursor.execute("SELECT banca_inicial FROM usuarios WHERE id = ?", (usuario_id,))
            banca_atual = cursor.fetchone()[0]
            conn.close()
        return render_template("editar_banca.html", mensagem=mensagem, banca_atual=banca_atual)

    # GET
    cursor.execute("SELECT banca_inicial FROM usuarios WHERE id = ?", (usuario_id,))
    result = cursor.fetchone()
    banca_atual = result[0] if result else 0.0
    conn.close()
    return render_template("editar_banca.html", banca_atual=banca_atual)


@app.route('/perfil')
def perfil():
    usuario_id = session.get('usuario_id')
    if not usuario_id:
        return redirect(url_for('login'))

    conn = conectar_banco()
    cursor = conn.cursor()

    # Recupera nome, email, banca inicial
    cursor.execute("""
        SELECT nome, email, banca_inicial
        FROM usuarios
        WHERE id = ?
    """, (usuario_id,))
    usuario = cursor.fetchone()

    if not usuario:
        return redirect(url_for('login'))

    nome, email, banca_inicial = usuario

    # Recupera todas as apostas para calcular banca atualizada
    cursor.execute("""
        SELECT valor_realizado
        FROM apostas
        WHERE usuario_id = ?
    """, (usuario_id,))
    apostas = cursor.fetchall()
    conn.close()

    lucro_total = sum([aposta['valor_realizado'] for aposta in apostas])
    banca_atual = banca_inicial + lucro_total

    # Evita divisão por zero
    rendimento_pct = ((banca_atual - banca_inicial) / banca_inicial * 100) if banca_inicial > 0 else 0

    return render_template('perfil.html',
                           nome=nome,
                           email=email,
                           banca_inicial=banca_inicial,
                           banca_atual=banca_atual,
                           rendimento_pct=rendimento_pct)





@app.template_filter('br_moeda')
def br_moeda(valor):
    try:
        return f"R$ {valor:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    except:
        return "R$ 0,00"



@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect('/login')

    usuario_id = session['usuario_id']
    conn = sqlite3.connect('banco.db')
    cursor = conn.cursor()

    cursor.execute("SELECT banca_inicial FROM usuarios WHERE id = ?", (usuario_id,))
    result = cursor.fetchone()
    banca_inicial = float(result[0]) if result and result[0] is not None else 0.0

    # Total de entradas (número de apostas feitas)
    cursor.execute("SELECT COUNT(*) FROM apostas WHERE usuario_id = ?", (usuario_id,))
    total_entradas = cursor.fetchone()[0] or 0

    # Total de greens (lucro positivo ou valor_realizado > stake)
    cursor.execute("""
        SELECT COUNT(*) FROM apostas 
        WHERE usuario_id = ? AND valor_realizado > 0
    """, (usuario_id,))
    total_greens = cursor.fetchone()[0] or 0

    # Total de reds (lucro negativo ou valor_realizado < stake)
    cursor.execute("""
        SELECT COUNT(*) FROM apostas 
        WHERE usuario_id = ? AND valor_realizado < 0
    """, (usuario_id,))
    total_reds = cursor.fetchone()[0] or 0

    # Caso queira considerar empates (valor_realizado == stake) pode adaptar depois

    cursor.execute("SELECT SUM(stake) FROM apostas WHERE usuario_id = ?", (usuario_id,))
    total_stake = cursor.fetchone()[0] or 0.0

    cursor.execute("SELECT SUM(valor_realizado) FROM apostas WHERE usuario_id = ?", (usuario_id,))
    total_valor_realizado = cursor.fetchone()[0] or 0.0

    lucro = total_valor_realizado 
    roi = (lucro / total_stake * 100) if total_stake > 0 else 0.0
    banca_atual = banca_inicial + lucro

    # Pega lucro por método
    cursor.execute("""
        SELECT metodo, SUM(valor_realizado) as lucro_metodo
        FROM apostas
        WHERE usuario_id = ?
        GROUP BY metodo
    """, (usuario_id,))
    lucro_por_metodo_rows = cursor.fetchall()

    # Separar dados para gráfico
    metodos = []
    lucros_metodo = []
    for metodo, lucro_met in lucro_por_metodo_rows:
        metodos.append(metodo if metodo else "Sem Método")
        lucros_metodo.append(round(lucro_met, 2))

    conn.close()

    return render_template('dashboard.html',
                           banca_inicial=banca_inicial,
                           total_entradas=total_entradas,
                           total_greens=total_greens,
                           total_reds=total_reds,
                           total_stake=total_stake,
                           total_valor_realizado=total_valor_realizado,
                           lucro=lucro,
                           roi=roi,
                           banca_atual=banca_atual,
                           metodos=metodos,
                           lucros_metodo=lucros_metodo)


    
@app.route('/historico')
def historico():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    usuario_id = session['usuario_id']
    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, data, metodo, casa, visitante, stake, odd, minuto_gol, valor_realizado
        FROM apostas
        WHERE usuario_id = ?
        ORDER BY data DESC
    """, (usuario_id,))
    apostas = cursor.fetchall()
    conn.close()

    return render_template('historico.html', apostas=apostas)

@app.route('/projecao', methods=['GET', 'POST'])
def projecao():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    resultados = None

    if request.method == 'POST':
        try:
            data_inicio = datetime.strptime(request.form['data_inicio'], '%Y-%m-%d')
            data_fim = datetime.strptime(request.form['data_fim'], '%Y-%m-%d')
            banca_inicial = float(request.form['banca_inicial'].replace(',', '.'))
            percentual_dia = float(request.form['percentual'].replace(',', '.')) / 100

            dias = (data_fim - data_inicio).days + 1
            banca_proj = banca_inicial
            banca_real_acumulada = banca_inicial
            resultados = []

            db = get_db()  # função que abre conexão SQLite e define row_factory

            usuario_id = session['usuario_id']

            for i in range(dias):
                data = data_inicio + timedelta(days=i)
                data_str = data.strftime('%Y-%m-%d')

                # Lucro projetado
                lucro_projetado = banca_proj * percentual_dia
                banca_projetada = banca_proj + lucro_projetado

                # Consulta lucro real do dia (ajuste conforme sua tabela!)
                query = """
                    SELECT COALESCE(SUM(valor_realizado), 0) AS lucro_real
                    FROM apostas
                    WHERE usuario_id = ? AND data = ?
                """
                cur = db.execute(query, (usuario_id, data_str))
                row = cur.fetchone()
                lucro_real_dia = row['lucro_real'] if row else 0

                # Atualiza banca real acumulada
                banca_real_acumulada += lucro_real_dia

                resultados.append({
                    'data': data.strftime('%d/%m/%Y'),
                    'banca_projetada': round(banca_projetada, 2),
                    'lucro_projetado_diario': round(lucro_projetado, 2),
                    'lucro_real_dia': round(lucro_real_dia, 2),
                    'banca_real_acumulada': round(banca_real_acumulada, 2)
                })

                # Atualiza banca projetada para próximo dia
                banca_proj = banca_projetada

        except Exception as e:
            return f"Erro ao calcular projeção: {e}"

    return render_template('projecao.html', resultados=resultados)


if __name__ == "__main__":
    criar_banco()
    app.run(debug=True)


