from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3  

app = Flask(__name__)
app.secret_key = 'erp_estoque_secret_key'
app.config['DATABASE'] = 'erp_estoque.db'

def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    # Tabela de Categorias
    conn.execute('''
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            descricao TEXT,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabela de Produtos
    conn.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            categoria_id INTEGER,
            codigo_barras TEXT UNIQUE,
            preco_custo DECIMAL(10,2),
            preco_venda DECIMAL(10,2),
            quantidade_minima INTEGER DEFAULT 10,
            quantidade_atual INTEGER DEFAULT 0,
            especificacoes_tecnicas TEXT,
            ativo BOOLEAN DEFAULT 1,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (categoria_id) REFERENCES categorias (id)
        )
    ''')
    
    # Tabela de Movimentações
    conn.execute('''
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id INTEGER NOT NULL,
            tipo TEXT NOT NULL, -- 'entrada' ou 'saida'
            quantidade INTEGER NOT NULL,
            valor_unitario DECIMAL(10,2),
            motivo TEXT NOT NULL, -- 'compra', 'venda', 'devolucao', 'transferencia', 'perda', 'ajuste'
            observacoes TEXT,
            usuario TEXT DEFAULT 'Sistema',
            data_movimentacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (produto_id) REFERENCES produtos (id)
        )
    ''')
    
    # Tabela de Alertas
    conn.execute('''
        CREATE TABLE IF NOT EXISTS alertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id INTEGER NOT NULL,
            tipo TEXT NOT NULL, -- 'estoque_baixo', 'estoque_zero', 'reposicao'
            mensagem TEXT NOT NULL,
            lido BOOLEAN DEFAULT 0,
            data_alerta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (produto_id) REFERENCES produtos (id)
        )
    ''')
    
    # Inserir categorias padrão
    categorias = [
        ('Eletrônicos', 'Produtos eletrônicos em geral'),
        ('Informática', 'Computadores, periféricos e acessórios'),
        ('Móveis', 'Móveis para escritório e residência'),
        ('Material Escritório', 'Material de consumo para escritório'),
        ('Limpeza', 'Produtos de limpeza e higiene')
    ]
    
    conn.executemany(
        'INSERT OR IGNORE INTO categorias (nome, descricao) VALUES (?, ?)',
        categorias
    )
    
    conn.commit()
    conn.close()

# ========== ROTAS PRINCIPAIS ==========

@app.route('/')
def dashboard():
    conn = get_db_connection()
    
    # Estatísticas gerais
    total_produtos = conn.execute('SELECT COUNT(*) FROM produtos WHERE ativo = 1').fetchone()[0]
    total_categorias = conn.execute('SELECT COUNT(*) FROM categorias').fetchone()[0]
    
    # Valor total do estoque
    estoque_valor = conn.execute('''
        SELECT SUM(p.quantidade_atual * p.preco_custo) 
        FROM produtos p 
        WHERE p.ativo = 1
    ''').fetchone()[0] or 0
    
    # Produtos com estoque baixo
    estoque_baixo = conn.execute('''
        SELECT COUNT(*) FROM produtos 
        WHERE quantidade_atual <= quantidade_minima AND ativo = 1
    ''').fetchone()[0]
    
    # Movimentações recentes
    movimentacoes_recentes = conn.execute('''
        SELECT m.*, p.nome as produto_nome 
        FROM movimentacoes m 
        JOIN produtos p ON m.produto_id = p.id 
        ORDER BY m.data_movimentacao DESC 
        LIMIT 10
    ''').fetchall()
    
    # Alertas não lidos
    alertas_nao_lidos = conn.execute('''
        SELECT COUNT(*) FROM alertas WHERE lido = 0
    ''').fetchone()[0]
    
    conn.close()
    
    return render_template('dashboard.html',
                         total_produtos=total_produtos,
                         total_categorias=total_categorias,
                         estoque_valor=estoque_valor,
                         estoque_baixo=estoque_baixo,
                         movimentacoes_recentes=movimentacoes_recentes,
                         alertas_nao_lidos=alertas_nao_lidos)

# ========== MÓDULO DE PRODUTOS ==========

@app.route('/produtos')
def listar_produtos():
    conn = get_db_connection()
    produtos = conn.execute('''
        SELECT p.*, c.nome as categoria_nome 
        FROM produtos p 
        LEFT JOIN categorias c ON p.categoria_id = c.id 
        WHERE p.ativo = 1
        ORDER BY p.nome
    ''').fetchall()
    conn.close()
    return render_template('produtos/listar.html', produtos=produtos)

@app.route('/produtos/cadastrar', methods=['GET', 'POST'])
def cadastrar_produto():
    conn = get_db_connection()
    
    if request.method == 'POST':
        nome = request.form['nome']
        categoria_id = request.form['categoria_id']
        codigo_barras = request.form.get('codigo_barras')
        preco_custo = float(request.form['preco_custo']) if request.form['preco_custo'] else 0
        preco_venda = float(request.form['preco_venda']) if request.form['preco_venda'] else 0
        quantidade_minima = int(request.form['quantidade_minima']) if request.form['quantidade_minima'] else 10
        especificacoes = request.form.get('especificacoes_tecnicas', '')
        
        try:
            conn.execute('''
                INSERT INTO produtos 
                (nome, categoria_id, codigo_barras, preco_custo, preco_venda, 
                 quantidade_minima, especificacoes_tecnicas)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (nome, categoria_id, codigo_barras, preco_custo, preco_venda, 
                  quantidade_minima, especificacoes))
            
            conn.commit()
            flash('Produto cadastrado com sucesso!', 'success')
            return redirect(url_for('listar_produtos'))
            
        except sqlite3.IntegrityError:
            flash('Erro: Código de barras já existe!', 'error')
    
    categorias = conn.execute('SELECT * FROM categorias ORDER BY nome').fetchall()
    conn.close()
    return render_template('produtos/cadastrar.html', categorias=categorias)

@app.route('/produtos/editar/<int:id>', methods=['GET', 'POST'])
def editar_produto(id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        nome = request.form['nome']
        categoria_id = request.form['categoria_id']
        codigo_barras = request.form.get('codigo_barras')
        preco_custo = float(request.form['preco_custo']) if request.form['preco_custo'] else 0
        preco_venda = float(request.form['preco_venda']) if request.form['preco_venda'] else 0
        quantidade_minima = int(request.form['quantidade_minima']) if request.form['quantidade_minima'] else 10
        especificacoes = request.form.get('especificacoes_tecnicas', '')
        ativo = request.form.get('ativo') == '1'
        
        try:
            conn.execute('''
                UPDATE produtos 
                SET nome = ?, categoria_id = ?, codigo_barras = ?, 
                    preco_custo = ?, preco_venda = ?, quantidade_minima = ?,
                    especificacoes_tecnicas = ?, ativo = ?, data_atualizacao = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (nome, categoria_id, codigo_barras, preco_custo, preco_venda,
                  quantidade_minima, especificacoes, ativo, id))
            
            conn.commit()
            flash('Produto atualizado com sucesso!', 'success')
            return redirect(url_for('listar_produtos'))
            
        except sqlite3.IntegrityError:
            flash('Erro: Código de barras já existe!', 'error')
    
    produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (id,)).fetchone()
    categorias = conn.execute('SELECT * FROM categorias ORDER BY nome').fetchall()
    conn.close()
    
    if produto is None:
        flash('Produto não encontrado!', 'error')
        return redirect(url_for('listar_produtos'))
    
    return render_template('produtos/editar.html', produto=produto, categorias=categorias)

@app.route('/produtos/deletar/<int:id>', methods=['GET', 'POST'])
def deletar_produto(id):
    conn = get_db_connection()
    
    # Buscar o produto para confirmar
    produto = conn.execute('SELECT * FROM produtos WHERE id=?', (id,)).fetchone()
    
    if request.method == 'POST':
        try:
            # Verificar se há movimentações associadas ao produto
            movimentacoes_count = conn.execute(
                'SELECT COUNT(*) FROM movimentacoes WHERE produto_id = ?', 
                (id,)
            ).fetchone()[0]
            
            if movimentacoes_count > 0:
                # Se houver movimentações, fazer soft delete (marcar como inativo)
                conn.execute('UPDATE produtos SET ativo = 0 WHERE id = ?', (id,))
                flash('Produto marcado como inativo (possui movimentações no histórico)', 'warning')
            else:
                # Se não houver movimentações, deletar permanentemente
                conn.execute('DELETE FROM produtos WHERE id = ?', (id,))
                flash('Produto excluído com sucesso!', 'success')
            
            conn.commit()
            return redirect(url_for('listar_produtos'))
            
        except sqlite3.Error as e:
            flash(f'Erro ao deletar produto: {str(e)}', 'error')
            conn.rollback()
    
    conn.close()
    return render_template('produtos/deletar.html', produto=produto)

# ========== MÓDULO DE MOVIMENTAÇÕES ==========

@app.route('/movimentacoes')
def listar_movimentacoes():
    conn = get_db_connection()
    movimentacoes = conn.execute('''
        SELECT m.*, p.nome as produto_nome, p.codigo_barras
        FROM movimentacoes m
        JOIN produtos p ON m.produto_id = p.id
        ORDER BY m.data_movimentacao DESC
    ''').fetchall()
    conn.close()
    return render_template('movimentacoes/listar.html', movimentacoes=movimentacoes)

@app.route('/movimentacoes/entrada', methods=['GET', 'POST'])
def entrada_estoque():
    conn = get_db_connection()
    
    if request.method == 'POST':
        produto_id = request.form['produto_id']
        quantidade = int(request.form['quantidade'])
        valor_unitario = float(request.form['valor_unitario']) if request.form['valor_unitario'] else 0
        motivo = request.form['motivo']
        observacoes = request.form.get('observacoes', '')
        
        # Registrar movimentação
        conn.execute('''
            INSERT INTO movimentacoes 
            (produto_id, tipo, quantidade, valor_unitario, motivo, observacoes)
            VALUES (?, 'entrada', ?, ?, ?, ?)
        ''', (produto_id, quantidade, valor_unitario, motivo, observacoes))
        
        # Atualizar estoque do produto
        conn.execute('''
            UPDATE produtos 
            SET quantidade_atual = quantidade_atual + ?, 
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (quantidade, produto_id))
        
        conn.commit()
        flash('Entrada de estoque registrada com sucesso!', 'success')
        return redirect(url_for('listar_movimentacoes'))
    
    produtos = conn.execute('SELECT * FROM produtos WHERE ativo = 1 ORDER BY nome').fetchall()
    conn.close()
    return render_template('movimentacoes/entrada.html', produtos=produtos)

@app.route('/movimentacoes/saida', methods=['GET', 'POST'])
def saida_estoque():
    conn = get_db_connection()
    
    if request.method == 'POST':
        produto_id = request.form['produto_id']
        quantidade = int(request.form['quantidade'])
        valor_unitario = float(request.form['valor_unitario']) if request.form['valor_unitario'] else 0
        motivo = request.form['motivo']
        observacoes = request.form.get('observacoes', '')
        
        # Verificar se há estoque suficiente
        produto = conn.execute('SELECT quantidade_atual FROM produtos WHERE id = ?', (produto_id,)).fetchone()
        
        if produto['quantidade_atual'] < quantidade:
            flash('Erro: Estoque insuficiente!', 'error')
        else:
            # Registrar movimentação
            conn.execute('''
                INSERT INTO movimentacoes 
                (produto_id, tipo, quantidade, valor_unitario, motivo, observacoes)
                VALUES (?, 'saida', ?, ?, ?, ?)
            ''', (produto_id, quantidade, valor_unitario, motivo, observacoes))
            
            # Atualizar estoque do produto
            conn.execute('''
                UPDATE produtos 
                SET quantidade_atual = quantidade_atual - ?, 
                    data_atualizacao = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (quantidade, produto_id))
            
            conn.commit()
            flash('Saída de estoque registrada com sucesso!', 'success')
            return redirect(url_for('listar_movimentacoes'))
    
    produtos = conn.execute('SELECT id, nome, codigo_barras, quantidade_atual FROM produtos WHERE ativo = 1 ORDER BY nome').fetchall()
    conn.close()
    return render_template('movimentacoes/saida.html', produtos=produtos)

# ========== CONSULTA EM TEMPO REAL ==========

@app.route('/api/estoque')
def api_estoque():
    conn = get_db_connection()
    produtos = conn.execute('''
        SELECT p.id, p.nome, p.codigo_barras, c.nome as categoria, 
               p.quantidade_atual, p.quantidade_minima, p.preco_custo,
               (p.quantidade_atual * p.preco_custo) as valor_total
        FROM produtos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        WHERE p.ativo = 1
        ORDER BY p.nome
    ''').fetchall()
    
    resultado = []
    for produto in produtos:
        resultado.append({
            'id': produto['id'],
            'nome': produto['nome'],
            'codigo_barras': produto['codigo_barras'],
            'categoria': produto['categoria'],
            'quantidade_atual': produto['quantidade_atual'],
            'quantidade_minima': produto['quantidade_minima'],
            'preco_custo': float(produto['preco_custo']) if produto['preco_custo'] else 0,
            'valor_total': float(produto['valor_total']) if produto['valor_total'] else 0,
            'estoque_baixo': produto['quantidade_atual'] <= produto['quantidade_minima']
        })
    
    conn.close()
    return jsonify(resultado)

# ========== ALERTAS INTELIGENTES ==========

@app.route('/alertas')
def listar_alertas():
    conn = get_db_connection()
    
    # Gerar alertas automaticamente
    gerar_alertas_automaticos(conn)
    
    alertas = conn.execute('''
        SELECT a.*, p.nome as produto_nome, p.codigo_barras
        FROM alertas a
        JOIN produtos p ON a.produto_id = p.id
        ORDER BY a.lido ASC, a.data_alerta DESC
    ''').fetchall()
    
    conn.close()
    return render_template('alertas.html', alertas=alertas)

def gerar_alertas_automaticos(conn):
    # Produtos com estoque baixo
    produtos_estoque_baixo = conn.execute('''
        SELECT id, nome, quantidade_atual, quantidade_minima
        FROM produtos 
        WHERE quantidade_atual <= quantidade_minima 
        AND ativo = 1
    ''').fetchall()
    
    for produto in produtos_estoque_baixo:
        # Verificar se já existe alerta não lido para este produto
        existe_alerta = conn.execute('''
            SELECT id FROM alertas 
            WHERE produto_id = ? AND tipo = 'estoque_baixo' AND lido = 0
        ''', (produto['id'],)).fetchone()
        
        if not existe_alerta:
            mensagem = f"Estoque baixo: {produto['nome']} ({produto['quantidade_atual']} unidades)"
            conn.execute('''
                INSERT INTO alertas (produto_id, tipo, mensagem)
                VALUES (?, 'estoque_baixo', ?)
            ''', (produto['id'], mensagem))
    
    # Produtos com estoque zerado
    produtos_estoque_zero = conn.execute('''
        SELECT id, nome FROM produtos 
        WHERE quantidade_atual = 0 AND ativo = 1
    ''').fetchall()
    
    for produto in produtos_estoque_zero:
        existe_alerta = conn.execute('''
            SELECT id FROM alertas 
            WHERE produto_id = ? AND tipo = 'estoque_zero' AND lido = 0
        ''', (produto['id'],)).fetchone()
        
        if not existe_alerta:
            mensagem = f"Estoque zerado: {produto['nome']}"
            conn.execute('''
                INSERT INTO alertas (produto_id, tipo, mensagem)
                VALUES (?, 'estoque_zero', ?)
            ''', (produto['id'], mensagem))
    
    conn.commit()


@app.route('/alerta/<int:id>/lido', methods=['POST'])
def marcar_lido(id):
    conn = get_db_connection()
    conn.execute('UPDATE alertas SET lido = 1 WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Alerta marcado como lido!', 'success')
    return redirect(url_for('listar_alertas'))

@app.route('/alertas/todos-lidos', methods=['POST'])
def marcar_todos_lidos():
    conn = get_db_connection()
    conn.execute('UPDATE alertas SET lido = 1 WHERE lido = 0')
    conn.commit()
    conn.close()
    flash('Todos os alertas foram marcados como lidos!', 'success')
    return redirect(url_for('listar_alertas'))

# ========== RELATÓRIOS GERENCIAIS ==========

@app.route('/relatorios')
def relatorios_gerenciais():
    conn = get_db_connection()
    
    # Movimentações por período (últimos 30 dias)
    movimentacoes_periodo = conn.execute('''
        SELECT tipo, motivo, COUNT(*) as quantidade, SUM(quantidade) as total_itens
        FROM movimentacoes 
        WHERE data_movimentacao >= date('now', '-30 days')
        GROUP BY tipo, motivo
    ''').fetchall()
    
    # Valorização do estoque
    valorizacao_estoque = conn.execute('''
        SELECT 
            SUM(quantidade_atual * preco_custo) as valor_total,
            COUNT(*) as total_produtos,
            SUM(CASE WHEN quantidade_atual <= quantidade_minima THEN 1 ELSE 0 END) as produtos_estoque_baixo
        FROM produtos 
        WHERE ativo = 1
    ''').fetchone()
    
    # Produtos mais movimentados
    produtos_movimentados = conn.execute('''
        SELECT p.nome, 
               SUM(CASE WHEN m.tipo = 'entrada' THEN m.quantidade ELSE 0 END) as entradas,
               SUM(CASE WHEN m.tipo = 'saida' THEN m.quantidade ELSE 0 END) as saidas,
               COUNT(m.id) as total_movimentacoes
        FROM produtos p
        LEFT JOIN movimentacoes m ON p.id = m.produto_id
        WHERE m.data_movimentacao >= date('now', '-30 days')
        GROUP BY p.id, p.nome
        ORDER BY total_movimentacoes DESC
        LIMIT 10
    ''').fetchall()
    
    conn.close()
    
    return render_template('relatorios/gerenciais.html',
                         movimentacoes_periodo=movimentacoes_periodo,
                         valorizacao_estoque=valorizacao_estoque,
                         produtos_movimentados=produtos_movimentados)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
