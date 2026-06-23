from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
import json
import os  # <-- 1. AGGIUNGI QUESTO IMPORT

app = Flask(__name__)
app.secret_key = "chiave_segreta_fantamondiale_123" 

# <-- 2. SOSTITUISCI LA TUA FUNZIONE CON QUESTA:
def get_db_connection():
    # Controlliamo se siamo online su Railway verificando se esiste la variabile MYSQLHOST
    if os.environ.get('MYSQLHOST'):
        # Configurazione per il server ONLINE
        return mysql.connector.connect(
            host=os.environ.get('MYSQLHOST'),
            user=os.environ.get('MYSQLUSER'),
            password=os.environ.get('MYSQLPASSWORD'),
            database=os.environ.get('MYSQLDATABASE'),
            port=int(os.environ.get('MYSQLPORT', 3306))
        )
    else:
        # Configurazione per il tuo computer LOCALE (resta identica a prima)
        return mysql.connector.connect(
            host="localhost",
            user="root",          
            password="",  
            database="fantacalcio"
        )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM utenti WHERE username = %s AND password = %s", (username, password))
        utente = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if utente:
            session['utente_id'] = utente['id']
            session['username'] = utente['username']
            session['nome_squadra'] = utente['nome_squadra']
            session['ruolo'] = utente['ruolo'] # 'admin' o 'utente'
            
            if utente['ruolo'] == 'admin':
                return redirect(url_for('admin'))
            else:
                return redirect(url_for('home_utente'))
        else:
            flash("Username o Password errati!", "danger")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# MODIFICHIAMO LA TUA VECCHIA HOME ROUTE PER GESTIRE IL PANNELLO UTENTE
@app.route('/')
def home_utente():
    if 'utente_id' not in session:
        return redirect(url_for('login'))
        
    # Se è un admin, lo rimandiamo comunque alla sua pagina
    if session.get('ruolo') == 'admin':
        return redirect(url_for('admin'))
        
    # --- FASE GET PER IL PANNELLO UTENTE (Copia parziale di quello che fa l'admin, ma filtrato) ---
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Recupero dati classifica, utenti e calendario (stessa logica dell'admin)
    cursor.execute("""
        SELECT u.*, 
               COALESCE(SUM(c.prezzo_acquisto), 0) AS crediti_spesi,
               (750 - COALESCE(SUM(c.prezzo_acquisto), 0)) AS crediti_restanti
        FROM utenti u
        LEFT JOIN calciatori c ON u.id = c.proprietario_id
        GROUP BY u.id
        ORDER BY u.nome_squadra ASC
    """)
    utenti = cursor.fetchall()

    cursor.execute("SELECT * FROM calciatori ORDER BY ruolo DESC, nome ASC")
    calciatori = cursor.fetchall()

    rose = {utente['id']: [] for utente in utenti}
    contatori = {utente['id']: {'P': 0, 'D': 0, 'C': 0, 'A': 0} for utente in utenti}
    rose_per_js = {utente['id']: {'P':[], 'D':[], 'C':[], 'A':[]} for utente in utenti}
    nomi_squadre = {u['id']: u['nome_squadra'] for u in utenti}
    nomi_calciatori = {c['id']: c['nome'] for c in calciatori}

    for giocatore in calciatori:
        prop_id = giocatore['proprietario_id']
        if prop_id in rose:
            rose[prop_id].append(giocatore)
            contatori[prop_id][giocatore['ruolo']] += 1
            rose_per_js[prop_id][giocatore['ruolo']].append({'id': giocatore['id'], 'nome': giocatore['nome']})

    cursor.execute("SELECT * FROM partite ORDER BY giornata DESC, id DESC")
    partite = cursor.fetchall()
    
    for p in partite:
        def get_nomi(json_str):
            try:
                ids = json.loads(json_str)
                return [nomi_calciatori.get(int(i), "Sconosciuto") for i in ids if i]
            except: return []
        p['nomi_casa'] = get_nomi(p['titolari_casa'])
        p['nomi_trasferta'] = get_nomi(p['titolari_trasferta'])
        p['nome_squadra_casa'] = nomi_squadre.get(p['squadra_casa_id'], "N/A")
        p['nome_squadra_trasferta'] = nomi_squadre.get(p['squadra_trasferta_id'], "N/A")

    # Riusiamo la logica della classifica che abbiamo creato nello scorso step
    classifica_dict = {u['id']: {'nome_squadra': u['nome_squadra'], 'punti': 0, 'vinte': 0, 'pareggiate': 0, 'perse': 0, 'goal_fatti': 0} for u in utenti}
    cursor.execute("SELECT * FROM partite")
    for p in cursor.fetchall():
        if p['gol_casa'] is not None and p['gol_trasferta'] is not None:
            id_casa = p['squadra_casa_id']
            id_trasferta = p['squadra_trasferta_id']
            g_casa = int(p['gol_casa'])
            g_trasferta = int(p['gol_trasferta'])
            if id_casa in classifica_dict: classifica_dict[id_casa]['goal_fatti'] += g_casa
            if id_trasferta in classifica_dict: classifica_dict[id_trasferta]['goal_fatti'] += g_trasferta
            if g_casa > g_trasferta:
                if id_casa in classifica_dict: classifica_dict[id_casa]['punti'] += 3; classifica_dict[id_casa]['vinte'] += 1
                if id_trasferta in classifica_dict: classifica_dict[id_trasferta]['perse'] += 1
            elif g_casa < g_trasferta:
                if id_trasferta in classifica_dict: classifica_dict[id_trasferta]['punti'] += 3; classifica_dict[id_trasferta]['vinte'] += 1
                if id_casa in classifica_dict: classifica_dict[id_casa]['perse'] += 1
            else:
                if id_casa in classifica_dict: classifica_dict[id_casa]['punti'] += 1; classifica_dict[id_casa]['pareggiate'] += 1
                if id_trasferta in classifica_dict: classifica_dict[id_trasferta]['punti'] += 1; classifica_dict[id_trasferta]['pareggiate'] += 1
    classifica_lista = list(classifica_dict.values())
    classifica_lista.sort(key=lambda x: (x['punti'], x['goal_fatti']), reverse=True)

      # AGGIUNGI QUESTO: Recupera gli ultimi 30 messaggi della bacheca con il nome di chi li ha scritti
    query_bacheca = """
        SELECT b.messaggio, b.data_invio, u.username 
        FROM bacheca b
        JOIN utenti u ON b.utente_id = u.id
        ORDER BY b.data_invio DESC
        LIMIT 30
    """
    cursor.execute(query_bacheca)
    messaggi_bacheca = cursor.fetchall()

    cursor.close()
    conn.close()
    
    # Passiamo i dati al nuovo file index.html dedicato agli utenti
    return render_template('index.html', utenti=utenti, rose=rose, contatori=contatori, rose_js=json.dumps(rose_per_js), partite=partite, classifica=classifica_lista, messaggi=messaggi_bacheca)


@app.route('/calcolatore')
def pagina_calcolatore():
    return render_template('calcolatore.html')

@app.route('/mercato', methods=['GET', 'POST'])
def mercato():
    if 'utente_id' not in session:
        return redirect(url_for('login'))
    if session.get('ruolo') == 'admin':
        return redirect(url_for('admin'))
        
    utente_id = session['utente_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    LIMITI_RUOLI = {'P': 3, 'D': 8, 'C': 8, 'A': 5}
    CREDITI_TOTALI_INIZIALI = 750

    # Recuperiamo i crediti spesi correnti (giocatori già in rosa)
    cursor.execute("SELECT COALESCE(SUM(prezzo_acquisto), 0) AS spesi FROM calciatori WHERE proprietario_id = %s", (utente_id,))
    crediti_spesi = cursor.fetchone()['spesi']
    
    # Recuperiamo i crediti attualmente "impegnati" nelle altre offerte segrete di questo utente
    cursor.execute("SELECT COALESCE(SUM(offerta), 0) AS impegnati FROM aste_mercato WHERE utente_id = %s", (utente_id,))
    crediti_impegnati = cursor.fetchone()['impegnati']
    
    crediti_restanti_reali = CREDITI_TOTALI_INIZIALI - crediti_spesi
    crediti_disponibili_per_offerte = crediti_restanti_reali - crediti_impegnati

    if request.method == 'POST':
        azione = request.form.get('azione')
        
        # --- AZIONE: SVINCOLA (Rimane immediato) ---
        if azione == 'svincola':
            calciatore_id = request.form.get('calciatore_id')
            cursor.execute("SELECT * FROM calciatori WHERE id = %s AND proprietario_id = %s", (calciatore_id, utente_id))
            giocatore = cursor.fetchone()
            if giocatore:
                cursor.execute("UPDATE calciatori SET proprietario_id = NULL, prezzo_acquisto = 0 WHERE id = %s", (calciatore_id,))
                conn.commit()
                flash(f"Hai svincolato {giocatore['nome']}. Recuperati {giocatore['prezzo_acquisto']} crediti!", "success")
            else:
                flash("Giocatore non trovato.", "danger")

        # --- AZIONE: INVIA OFFERTA SEGRETA ---
        elif azione == 'acquista':
            calciatore_id = request.form.get('calciatore_id')
            prezzo_offerta = int(request.form.get('prezzo_offerta', 1))
            
            cursor.execute("SELECT * FROM calciatori WHERE id = %s AND proprietario_id IS NULL", (calciatore_id,))
            giocatore = cursor.fetchone()
            
            if not giocatore:
                flash("Questo calciatore non è più sul mercato!", "danger")
            else:
                # Controlliamo se avevamo già fatto un'offerta per lui (in quel caso la stiamo modificando)
                cursor.execute("SELECT offerta FROM aste_mercato WHERE utente_id = %s AND calciatore_id = %s", (utente_id, calciatore_id))
                vecchia_offerta_res = cursor.fetchone()
                vecchia_offerta = vecchia_offerta_res['offerta'] if vecchia_offerta_res else 0
                
                # Ricalcoliamo la disponibilità considerando l'eventuale modifica
                disponibilita_effettiva = crediti_disponibili_per_offerte + vecchia_offerta
                
                if prezzo_offerta > disponibilita_effettiva:
                    flash("Non hai abbastanza crediti liberi! Controlla le altre offerte attive.", "danger")
                else:
                    # Inseriamo o aggiorniamo l'offerta segreta
                    cursor.execute("""
                        INSERT INTO aste_mercato (utente_id, calciatore_id, offerta) 
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE offerta = %s
                    """, (utente_id, calciatore_id, prezzo_offerta, prezzo_offerta))
                    conn.commit()
                    flash(f"Offerta segreta di {prezzo_offerta} cr registrata per {giocatore['nome']}! 🤫", "success")

        # --- AZIONE: ANNULLA OFFERTA ---
        elif action := request.form.get('azione') == 'annulla_offerta':
            calciatore_id = request.form.get('calciatore_id')
            cursor.execute("DELETE FROM aste_mercato WHERE utente_id = %s AND calciatore_id = %s", (utente_id, calciatore_id))
            conn.commit()
            flash("Offerta annullata correttamente.", "info")

        cursor.close()
        conn.close()
        return redirect(url_for('mercato'))

    # DATI PER IL TEMPLATE
    cursor.execute("SELECT * FROM calciatori WHERE proprietario_id = %s ORDER BY ruolo DESC, nome ASC", (utente_id,))
    mia_rosa = cursor.fetchall()
    
    cursor.execute("SELECT * FROM calciatori WHERE proprietario_id IS NULL ORDER BY ruolo DESC, nome ASC")
    svincolati = cursor.fetchall()
    
    # Recuperiamo le offerte attive di questo utente per mostrarle nella grafica
    cursor.execute("""
        SELECT am.*, c.nome, c.ruolo 
        FROM aste_mercato am 
        JOIN calciatori c ON am.calciatore_id = c.id 
        WHERE am.utente_id = %s
    """, (utente_id,))
    mie_offerte = cursor.fetchall()
    mappa_offerte = {o['calciatore_id']: o['offerta'] for o in mie_offerte}

    cursor.close()
    conn.close()
    
    return render_template('mercato.html', mia_rosa=mia_rosa, svincolati=svincolati, crediti_restanti=crediti_disponibili_per_offerte, mie_offerte=mie_offerte, mappa_offerte=mappa_offerte)

@app.route('/storico')
def storico():
    if 'utente_id' not in session:
        return redirect(url_for('login'))
        
    utente_id = session['utente_id']
    giornata_selezionata = request.args.get('giornata', type=int)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Trova quali giornate sono disponibili nello storico per creare il menu a tendina
    cursor.execute("SELECT DISTINCT giornata FROM storico_formazioni ORDER BY giornata DESC")
    giornate_disponibili = [row['giornata'] for row in cursor.fetchall()]
    
    # Se l'utente non ha selezionato una giornata, mostriamo l'ultima disponibile
    if not giornata_selezionata and giornate_disponibili:
        giornata_selezionata = giornate_disponibili[0]
        
    formazione_storica = []
    punteggio_totale_giornata = 0
    
    if giornata_selezionata:
        # 2. Recupera la formazione dell'utente per quella specifica giornata passata
        cursor.execute("""
            SELECT sf.*, c.nome, c.ruolo 
            FROM storico_formazioni sf
            JOIN calciatori c ON sf.calciatore_id = c.id
            WHERE sf.utente_id = %s AND sf.giornata = %s
            ORDER BY sf.posizione DESC, c.ruolo DESC
        """, (utente_id, giornata_selezionata))
        formazione_storica = cursor.fetchall()
        
        # 3. Calcola il totale dei punti fatti in quella vecchia giornata (somma solo i titolari)
        cursor.execute("""
            SELECT SUM(punti_totali_giocatore) AS totale 
            FROM storico_formazioni 
            WHERE utente_id = %s AND giornata = %s AND posizione = 'titolare'
        """, (utente_id, giornata_selezionata))
        res_punti = cursor.fetchone()
        punteggio_totale_giornata = res_punti['totale'] if res_punti['totale'] else 0

    cursor.close()
    conn.close()
    
    return render_template('storico.html', 
                           giornate=giornate_disponibili, 
                           giornata_selezionata=giornata_selezionata, 
                           formazione=formazione_storica,
                           punteggio_totale=punteggio_totale_giornata)

# ==========================================
# FUNZIONE: INVIA FORMAZIONE (UTENTE)
# ==========================================
@app.route('/schiera-formazione', methods=['GET', 'POST'])
def schiera_formazione():
    if 'utente_id' not in session:
        return redirect(url_for('login'))
    
    utente_id = session['utente_id']
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        giornata = request.form.get('giornata') # Recupera il numero della giornata
        modulo = request.form.get('modulo')
        portiere = request.form.get('por_1')
        
        difensori = [request.form.get(f'dif_{i}') for i in range(1, 6) if request.form.get(f'dif_{i}')]
        centrocampisti = [request.form.get(f'cen_{i}') for i in range(1, 6) if request.form.get(f'cen_{i}')]
        attaccanti = [request.form.get(f'att_{i}') for i in range(1, 4) if request.form.get(f'att_{i}')]
        
        lista_titolari = [portiere] + difensori + centrocampisti + attaccanti
        
        if len(lista_titolari) != len(set(lista_titolari)):
            flash("Errore: Non puoi schierare lo stesso giocatore più di una volta! 🚫", "danger")
            return redirect(url_for('schiera_formazione'))
            
        titolari_json = json.dumps(lista_titolari)
        
        # Query aggiornata con la colonna 'giornata'
        query = """
            INSERT INTO formazioni_inviate (utente_id, giornata, modulo, titolari)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE modulo=%s, titolari=%s
        """
        cursor.execute(query, (utente_id, giornata, modulo, titolari_json, modulo, titolari_json))
        conn.commit()
        cursor.close()
        conn.close()
        
        flash(f"Formazione per la Giornata {giornata} consegnata! 🚀", "success")
        return redirect(url_for('home_utente'))
        
    cursor.execute("SELECT * FROM calciatori WHERE proprietario_id = %s ORDER BY nome ASC", (utente_id,))
    miei_calciatori = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('formazione.html', miei_calciatori=miei_calciatori)


# ==========================================
# FUNZIONE: PANNELLO FORMAZIONI (ADMIN)
# ==========================================
@app.route('/admin/formazioni')
def admin_formazioni():
    if 'utente_id' not in session or session.get('ruolo') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Ordiniamo prima per Giornata più recente, poi per data di invio
    query = """
        SELECT f.*, u.username 
        FROM formazioni_inviate f
        JOIN utenti u ON f.utente_id = u.id
        ORDER BY f.giornata DESC, f.data_invio DESC
    """
    cursor.execute(query)
    formazioni_ricevute = cursor.fetchall()
    
    for f in formazioni_ricevute:
        if f['titolari']:
            f['titolari'] = json.loads(f['titolari'])
        else:
            f['titolari'] = []
            
    cursor.close()
    conn.close()
    
    return render_template('admin_formazioni.html', formazioni=formazioni_ricevute)

# ==========================================
# GESTIONE SCAMBI (PROPOSTA E VISUALIZZAZIONE)
# ==========================================
@app.route('/scambi', methods=['GET', 'POST'])
def gestione_scambi():
    if 'utente_id' not in session:
        return redirect(url_for('login'))
    
    utente_id = session['utente_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        # Recuperiamo i dati dal form di proposta scambio
        calciatore_offerto_id = request.form.get('calciatore_offerto')
        calciatore_richiesto_id = request.form.get('calciatore_richiesto')
        
        # Trova chi è il proprietario del calciatore richiesto
        cursor.execute("SELECT proprietario_id FROM calciatori WHERE id = %s", (calciatore_richiesto_id,))
        ricevente = cursor.fetchone()
        
        if ricevente and ricevente['proprietario_id'] != utente_id:
            utente_riceve_id = ricevente['proprietario_id']
            
            # Inserisce la proposta di scambio
            query = """
                INSERT INTO scambi (utente_propone_id, utente_riceve_id, calciatore_offerto_id, calciatore_richiesto_id)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (utente_id, utente_riceve_id, calciatore_offerto_id, calciatore_richiesto_id))
            conn.commit()
            flash("Proposta di scambio inviata! 🤝", "success")
        else:
            flash("Errore nella proposta di scambio.", "danger")
            
        return redirect(url_for('gestione_scambi'))

    # --- CODICE PER IL GET (Visualizzazione della pagina) ---
    # 1. Miei calciatori da offrire
    cursor.execute("SELECT id, nome, ruolo FROM calciatori WHERE proprietario_id = %s ORDER BY ruolo, nome", (utente_id,))
    miei_calciatori = cursor.fetchall()
    
    # 2. Calciatori degli ALTRI utenti da poter richiedere
    cursor.execute("""
        SELECT c.id, c.nome, c.ruolo, u.username 
        FROM calciatori c 
        JOIN utenti u ON c.proprietario_id = u.id 
        WHERE c.proprietario_id != %s 
        ORDER BY u.username, c.ruolo
    """, (utente_id,))
    calciatori_altri = cursor.fetchall()
    
    # 3. Scambi RICEVUTI (in attesa)
    cursor.execute("""
        SELECT s.id, u.username AS mittente, co.nome AS offerto, cr.nome AS richiesto, s.data_proposta
        FROM scambi s
        JOIN utenti u ON s.utente_propone_id = u.id
        JOIN calciatori co ON s.calciatore_offerto_id = co.id
        JOIN calciatori cr ON s.calciatore_richiesto_id = cr.id
        WHERE s.utente_riceve_id = %s AND s.stato = 'in_attesa'
    """, (utente_id,))
    scambi_ricevuti = cursor.fetchall()
    
    # 4. Storico delle mie proposte inviate
    cursor.execute("""
        SELECT s.stato, u.username AS destinatario, co.nome AS offerto, cr.nome AS richiesto
        FROM scambi s
        JOIN utenti u ON s.utente_riceve_id = u.id
        JOIN calciatori co ON s.calciatore_offerto_id = co.id
        JOIN calciatori cr ON s.calciatore_richiesto_id = cr.id
        WHERE s.utente_propone_id = %s
        ORDER BY s.data_proposta DESC
    """, (utente_id,))
    scambi_inviati = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('scambi.html', miei_calciatori=miei_calciatori, calciatori_altri=calciatori_altri, ricevuti=scambi_ricevuti, inviati=scambi_inviati)


# ==========================================
# ROTTA PER ACCETTARE O RIFIUTARE LO SCAMBIO
# ==========================================
@app.route('/scambi/rispondi/<int:scambio_id>/<string:azione>', methods=['POST'])
def rispondi_scambio(scambio_id, azione):
    if 'utente_id' not in session:
        return redirect(url_for('login'))
        
    utente_id = session['utente_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Recuperiamo lo scambio per verificare che il ricevente sia l'utente attuale
    cursor.execute("SELECT * FROM scambi WHERE id = %s AND utente_riceve_id = %s AND stato = 'in_attesa'", (scambio_id, utente_id))
    scambio = cursor.fetchone()
    
    if scambio:
        if azione == 'accetta':
            # 1. Aggiorna lo stato dello scambio
            cursor.execute("UPDATE scambi SET stato = 'accettato' WHERE id = %s", (scambio_id,))
            
            # 2. SCAMBIO PROPRIETARI: Il calciatore offerto va a chi ha ricevuto la proposta
            cursor.execute("UPDATE calciatori SET proprietario_id = %s WHERE id = %s", (scambio['utente_riceve_id'], scambio['calciatore_offerto_id']))
            
            # 3. SCAMBIO PROPRIETARI: Il calciatore richiesto va a chi ha proposto lo scambio
            cursor.execute("UPDATE calciatori SET proprietario_id = %s WHERE id = %s", (scambio['utente_propone_id'], scambio['calciatore_richiesto_id']))
            
            # 4. Opzionale: Rifiuta automaticamente altri scambi in attesa che includono questi due giocatori
            cursor.execute("""
                UPDATE scambi SET stato = 'rifiutato' 
                WHERE id != %s AND stato = 'in_attesa' AND 
                (calciatore_offerto_id IN (%s, %s) OR calciatore_richiesto_id IN (%s, %s))
            """, (scambio_id, scambio['calciatore_offerto_id'], scambio['calciatore_richiesto_id'], scambio['calciatore_offerto_id'], scambio['calciatore_richiesto_id']))
            
            flash("Scambio concluso con successo! Squadre aggiornate. 🔁", "success")
            
        elif azione == 'rifiuta':
            cursor.execute("UPDATE scambi SET stato = 'rifiutato' WHERE id = %s", (scambio_id,))
            flash("Scambio rifiutato.", "info")
            
        conn.commit()
    else:
        flash("Scambio non trovato o autorizzazione negata.", "danger")
        
    cursor.close()
    conn.close()
    return redirect(url_for('gestione_scambi'))

# ==========================================
# NUOVA ROTTA: INVIA MESSAGGIO IN BACHECA
# ==========================================
@app.route('/bacheca/invia', methods=['POST'])
def invia_messaggio_bacheca():
    if 'utente_id' not in session:
        return redirect(url_for('login'))
        
    utente_id = session['utente_id']
    testo_messaggio = request.form.get('messaggio_testo')
    
    # Evita di salvare messaggi vuoti
    if testo_messaggio and testo_messaggio.strip():
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = "INSERT INTO bacheca (utente_id, messaggio) VALUES (%s, %s)"
        cursor.execute(query, (utente_id, testo_messaggio.strip()))
        
        conn.commit()
        cursor.close()
        conn.close()
        
    # Torna automaticamente alla home dopo aver inviato il messaggio
    return redirect(url_for('home_utente'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'utente_id' not in session or session.get('ruolo') != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)



    # AUTO-CREAZIONE TABELLA PARTITE (Così non devi usare phpMyAdmin)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS partite (
            id INT AUTO_INCREMENT PRIMARY KEY,
            giornata INT NOT NULL,
            squadra_casa_id INT,
            squadra_trasferta_id INT,
            modulo_casa VARCHAR(10),
            modulo_trasferta VARCHAR(10),
            titolari_casa TEXT,
            titolari_trasferta TEXT
        )
    """)
    conn.commit()

    try:
        cursor.execute("ALTER TABLE utenti ADD COLUMN password VARCHAR(255) DEFAULT '123'")
        cursor.execute("ALTER TABLE utenti ADD COLUMN ruolo VARCHAR(20) DEFAULT 'utente'")
        conn.commit()
    except:
        pass

    # AGGIUNTA: Tabella per salvare i voti dei calciatori per ogni giornata
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voti (
            id INT AUTO_INCREMENT PRIMARY KEY,
            calciatore_id INT NOT NULL,
            giornata INT NOT NULL,
            voto FLOAT NOT NULL,
            bonus_malus FLOAT DEFAULT 0,
            FOREIGN KEY (calciatore_id) REFERENCES calciatori(id),
            UNIQUE KEY_calciatore_giornata (calciatore_id, giornata)
        )
    """)
    conn.commit()

    try:
        cursor.execute("ALTER TABLE utenti ADD COLUMN password VARCHAR(255) DEFAULT '123'")
        cursor.execute("ALTER TABLE utenti ADD COLUMN ruolo VARCHAR(20) DEFAULT 'utente'")
        conn.commit()
    except:
        pass

    # AGGIUNTA: Colonne nelle partite per salvare il punteggio totale (somma voti) se non esistono
    try:
        cursor.execute("ALTER TABLE partite ADD COLUMN totale_casa FLOAT DEFAULT 0")
        cursor.execute("ALTER TABLE partite ADD COLUMN totale_trasferta FLOAT DEFAULT 0")
        conn.commit()
    except:
        pass

    if request.method == 'POST':
        azione = request.form.get('azione')

        # --- NUOVA AZIONE ADMIN: APRI BUSTE ---
        if azione == 'risolvi_buste':
            # 1. Recuperiamo l'ordine della classifica inversa (chi ha meno punti ha la priorità in caso di pareggio)
            # Recuperiamo tutti i punteggi correnti dalla classifica per decidere i pareggi
            # Nota: riutilizziamo una query semplice sui punti degli utenti
            cursor.execute("SELECT id FROM utenti")
            utenti_lista = cursor.fetchall()
            
            # Calcolo classifica rapido per spareggi (squadra peggiore vince lo spareggio)
            classifica_ordinata_peggiore = []
            # (Per semplicità in caso di pareggio useremo l'ID utente più alto, o puoi implementare la classifica reale. 
            # Per rendere il codice leggero e non bloccarsi, ordiniamo per ID decrescente come criterio di spareggio veloce)

            # 2. Troviamo tutti i calciatori che hanno ricevuto almeno un'offerta
            cursor.execute("SELECT DISTINCT calciatore_id FROM aste_mercato")
            calciatori_con_offerte = cursor.fetchall()
            
            for c in calciatori_con_offerte:
                cid = c['calciatore_id']
                
                # Prendiamo tutte le offerte per questo specifico calciatore, ordinate per offerta DECRESCENTE
                # In caso di parità di offerta, l'utente con l'ID più alto (o inserisci logica classifica) viene estratto prima
                cursor.execute("""
                    SELECT am.*, c.ruolo, c.nome 
                    FROM aste_mercato am
                    JOIN calciatori c ON am.calciatore_id = c.id
                    WHERE am.calciatore_id = %s 
                    ORDER BY am.offerta DESC, am.utente_id DESC
                """, (cid,))
                offerte = cursor.fetchall()
                
                if offerte:
                    vincitore = offerte[0] # Il primo è chi ha offerto di più!
                    
                    # Controlliamo se il vincitore ha spazio in rosa per quel ruolo
                    LIMITI = {'P': 3, 'D': 8, 'C': 8, 'A': 5}
                    cursor.execute("SELECT COUNT(*) AS tot FROM calciatori WHERE proprietario_id = %s AND ruolo = %s", (vincitore['utente_id'], vincitore['ruolo']))
                    spazio_occupato = cursor.fetchone()['tot']
                    
                    if spazio_occupato < LIMITI[vincitore['ruolo']]:
                        # Assegniamo il giocatore!
                        cursor.execute("UPDATE calciatori SET proprietario_id = %s, prezzo_acquisto = %s WHERE id = %s", 
                                       (vincitore['utente_id'], vincitore['offerta'], vincitore['calciatore_id']))
                        conn.commit()
            
            # Svuotiamo la tabella delle aste visto che il mercato è stato elaborato
            cursor.execute("TRUNCATE TABLE aste_mercato")
            conn.commit()
            flash("Buste aperte! I calciatori sono stati assegnati ai migliori offerenti. 🏆", "success")

        try:
            if azione == 'crea_utente':
                username = request.form.get('username')
                nome_squadra = request.form.get('nome_squadra')
                cursor.execute(
                    "INSERT INTO utenti (username, password, nome_squadra) VALUES (%s, '123', %s)",
                    (username, nome_squadra)
                )
                conn.commit()

            elif azione == 'crea_calciatore':
                nome = request.form.get('nome')
                ruolo = request.form.get('ruolo')
                nazionale = request.form.get('nazionale')
                quotazione = request.form.get('quotazione')
                cursor.execute(
                    "INSERT INTO calciatori (nome, ruolo, nazionale, quotazione) VALUES (%s, %s, %s, %s)",
                    (nome, ruolo, nazionale, quotazione)
                )
                conn.commit()

            elif azione == 'assegna_calciatore':
                calciatore_id = request.form.get('calciatore_id')
                utente_id = request.form.get('utente_id')
                prezzo_acquisto = request.form.get('prezzo_acquisto')
                
                if utente_id == "":
                    utente_id = None
                    prezzo_acquisto = None
                else:
                    if not prezzo_acquisto:
                        prezzo_acquisto = 0

                    cursor.execute("SELECT ruolo, proprietario_id FROM calciatori WHERE id = %s", (calciatore_id,))
                    calciatore_db = cursor.fetchone()
                    ruolo_calciatore = calciatore_db['ruolo']
                    vecchio_proprietario = calciatore_db['proprietario_id']

                    if str(vecchio_proprietario) != str(utente_id):
                        cursor.execute("""
                            SELECT COUNT(*) AS conteggio 
                            FROM calciatori 
                            WHERE proprietario_id = %s AND ruolo = %s
                        """, (utente_id, ruolo_calciatore))
                        conteggio_attuale = cursor.fetchone()['conteggio']

                        limiti = {'P': 3, 'D': 8, 'C': 8, 'A': 6}
                        if conteggio_attuale >= limiti[ruolo_calciatore]:
                            raise Exception(f"L'allenatore ha già riempito gli slot per il ruolo {ruolo_calciatore} (Limite: {limiti[ruolo_calciatore]}).")

                cursor.execute(
                    "UPDATE calciatori SET proprietario_id = %s, prezzo_acquisto = %s WHERE id = %s",
                    (utente_id, prezzo_acquisto, calciatore_id)
                )
                conn.commit()

            # NUOVA AZIONE: SALVA PARTITA E FORMAZIONI
            elif azione == 'salva_partita':
                giornata = request.form.get('giornata')
                squadra_casa_id = request.form.get('squadra_casa')
                squadra_trasferta_id = request.form.get('squadra_trasferta')
                modulo_casa = request.form.get('modulo_casa')
                modulo_trasferta = request.form.get('modulo_trasferta')

                # Raccogliamo gli 11 titolari dai menu a tendina
                titolari_casa = [request.form.get(f'casa_titolare_{i}') for i in range(1, 12)]
                titolari_trasferta = [request.form.get(f'trasferta_titolare_{i}') for i in range(1, 12)]

                cursor.execute("""
                    INSERT INTO partite (giornata, squadra_casa_id, squadra_trasferta_id, modulo_casa, modulo_trasferta, titolari_casa, titolari_trasferta)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (giornata, squadra_casa_id, squadra_trasferta_id, modulo_casa, modulo_trasferta, json.dumps(titolari_casa), json.dumps(titolari_trasferta)))
                conn.commit()

            # NUOVA AZIONE: AGGIORNA RISULTATO DELLA PARTITA
            # NUOVA AZIONE: AGGIORNA RISULTATO DELLA PARTITA (Corretto!)
            elif azione == 'aggiorna_risultato':
                partita_id = request.form.get('partita_id')
                gol_casa = request.form.get('gol_casa')
                gol_trasferta = request.form.get('gol_trasferta')

                cursor.execute("""
                    UPDATE partite 
                    SET gol_casa = %s, gol_trasferta = %s 
                    WHERE id = %s
                """, (gol_casa, gol_trasferta, partita_id))
                
                conn.commit()

            # NUOVA AZIONE: SALVA VOTI GIORNATA E CALCOLA RISULTATI AUTOMATICAMENTE
            elif azione == 'salva_voti_giornata':
                giornata_voti = int(request.form.get('giornata_voti'))
                
                # 1. Recuperiamo tutti i calciatori per ciclare i campi del form
                cursor.execute("SELECT id FROM calciatori")
                tutti_i_calciatori = cursor.fetchall()
                
                for calc in tutti_i_calciatori:
                    c_id = calc['id']
                    voto_input = request.form.get(f'voto_{c_id}')
                    bonus_input = request.form.get(f'bonus_{c_id}')
                    
                    # Se è stato inserito un voto (non vuoto)
                    if voto_input and voto_input.strip() != "":
                        voto = float(voto_input)
                        bonus = float(bonus_input) if bonus_input else 0.0
                        
                        # Inseriamo o aggiorniamo il voto del giocatore per quella giornata
                        cursor.execute("""
                            INSERT INTO voti (calciatore_id, giornata, voto, bonus_malus)
                            VALUES (%s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE voto = VALUES(voto), bonus_malus = VALUES(bonus_malus)
                        """, (c_id, giornata_voti, voto, bonus))

                conn.commit()

                # 2. CALCOLO AUTOMATICO DELLE PARTITE DI QUESTA GIORNATA
                cursor.execute("SELECT * FROM partite WHERE giornata = %s", (giornata_voti,))
                partite_giornata = cursor.fetchall()
                
                # Recuperiamo tutti i voti appena inseriti in un dizionario comodo {calciatore_id: voto_totale}
                cursor.execute("SELECT calciatore_id, (voto + bonus_malus) as fanta_voto FROM voti WHERE giornata = %s", (giornata_voti,))
                voti_mappa = {v['calciatore_id']: v['fanta_voto'] for v in cursor.fetchall()}

                for part in partite_giornata:
                    try:
                        ids_casa = json.loads(part['titolari_casa'])
                        ids_trasferta = json.loads(part['titolari_trasferta'])
                    except:
                        continue # Se non ci sono formazioni schierate salta la partita
                    
                    # Sommiamo i voti degli 11 titolari (se manca il voto contiamo un d'ufficio o 0, in questo caso 0)
                    totale_casa = sum(float(voti_mappa.get(int(i), 0)) for i in ids_casa if i)
                    totale_trasferta = sum(float(voti_mappa.get(int(i), 0)) for i in ids_trasferta if i)
                    
                    # Funzione interna per calcolare i gol in base alle soglie
                    def calcola_gol(punteggio):
                        if punteggio < 66:
                            return 0
                        return int(1 + (punteggio - 66) // 6) # 66=1 gol, 72=2 gol, 78=3 gol, ecc.
                    
                    gol_casa = calcola_gol(totale_casa) if totale_casa > 0 else None
                    gol_trasferta = calcola_gol(totale_trasferta) if totale_trasferta > 0 else None
                    
                    # Aggiorniamo la partita con i totali calcolati e i gol generati
                    cursor.execute("""
                        UPDATE partite 
                        SET totale_casa = %s, totale_trasferta = %s, gol_casa = %s, gol_trasferta = %s 
                        WHERE id = %s
                    """, (totale_casa, totale_trasferta, gol_casa, gol_trasferta, part['id']))
                    
                    # =========================================================================
                    # 🚀 [INSERITO QUI] SALVATAGGIO NELLO STORICO FORMAZIONI DI GIORNATA
                    # =========================================================================
                    if part['squadra_casa_id']:
                        cursor.execute("DELETE FROM storico_formazioni WHERE giornata = %s AND utente_id = %s", (giornata_voti, part['squadra_casa_id']))
                    if part['squadra_trasferta_id']:
                        cursor.execute("DELETE FROM storico_formazioni WHERE giornata = %s AND utente_id = %s", (giornata_voti, part['squadra_trasferta_id']))
                    
                    # Salva i titolari in casa
                    if part['squadra_casa_id'] and ids_casa:
                        for c_id in ids_casa:
                            if c_id:
                                cursor.execute("SELECT voto, bonus_malus FROM voti WHERE calciatore_id = %s AND giornata = %s", (int(c_id), giornata_voti))
                                v_dati = cursor.fetchone()
                                v_base = v_dati['voto'] if v_dati else 0.0
                                b_malus = v_dati['bonus_malus'] if v_dati else 0.0
                                fanta_voto = v_base + b_malus
                                cursor.execute("""
                                    INSERT INTO storico_formazioni (giornata, utente_id, calciatore_id, posizione, voto, punti_totali_giocatore)
                                    VALUES (%s, %s, %s, 'titolare', %s, %s)
                                """, (giornata_voti, part['squadra_casa_id'], int(c_id), v_base, fanta_voto))

                    # Salva i titolari in trasferta
                    if part['squadra_trasferta_id'] and ids_trasferta:
                        for c_id in ids_trasferta:
                            if c_id:
                                cursor.execute("SELECT voto, bonus_malus FROM voti WHERE calciatore_id = %s AND giornata = %s", (int(c_id), giornata_voti))
                                v_dati = cursor.fetchone()
                                v_base = v_dati['voto'] if v_dati else 0.0
                                b_malus = v_dati['bonus_malus'] if v_dati else 0.0
                                fanta_voto = v_base + b_malus
                                cursor.execute("""
                                    INSERT INTO storico_formazioni (giornata, utente_id, calciatore_id, posizione, voto, punti_totali_giocatore)
                                    VALUES (%s, %s, %s, 'titolare', %s, %s)
                                """, (giornata_voti, part['squadra_trasferta_id'], int(c_id), v_base, fanta_voto))
                    # =========================================================================
                
                conn.commit()

        except Exception as e:
            cursor.close()
            conn.close()
            return f"<h1>Errore:</h1><p>{str(e)}</p>"

        return redirect(url_for('admin'))

    # --- FASE GET ---
    cursor.execute("""
        SELECT u.*, 
               COALESCE(SUM(c.prezzo_acquisto), 0) AS crediti_spesi,
               (750 - COALESCE(SUM(c.prezzo_acquisto), 0)) AS crediti_restanti
        FROM utenti u
        LEFT JOIN calciatori c ON u.id = c.proprietario_id
        GROUP BY u.id
        ORDER BY u.nome_squadra ASC
    """)
    utenti = cursor.fetchall()

    cursor.execute("SELECT * FROM calciatori ORDER BY ruolo DESC, nome ASC")
    calciatori = cursor.fetchall()

    # Prepariamo le rose e i contatori
    rose = {utente['id']: [] for utente in utenti}
    contatori = {utente['id']: {'P': 0, 'D': 0, 'C': 0, 'A': 0} for utente in utenti}
    
    # STRUTTURA OTTIMIZZATA PER IL JAVASCRIPT
    rose_per_js = {utente['id']: {'P':[], 'D':[], 'C':[], 'A':[]} for utente in utenti}

    # Creiamo un dizionario per mappare ID squadra -> Nome squadra (per il calendario)
    nomi_squadre = {u['id']: u['nome_squadra'] for u in utenti}
    # Creiamo un dizionario per mappare ID giocatore -> Nome giocatore (per il calendario)
    nomi_calciatori = {c['id']: c['nome'] for c in calciatori}

    for giocatore in calciatori:
        prop_id = giocatore['proprietario_id']
        if prop_id in rose:
            rose[prop_id].append(giocatore)
            contatori[prop_id][giocatore['ruolo']] += 1
            rose_per_js[prop_id][giocatore['ruolo']].append({
                'id': giocatore['id'], 
                'nome': giocatore['nome']
            })

    # RECUPERO PARTITE PER IL CALENDARIO
    cursor.execute("SELECT * FROM partite ORDER BY giornata DESC, id DESC")
    partite = cursor.fetchall()
    
    # Decodifichiamo i JSON per visualizzare i nomi nel template
    for p in partite:
        # Convertiamo la lista di ID (JSON) in nomi
        def get_nomi(json_str):
            try:
                ids = json.loads(json_str)
                return [nomi_calciatori.get(int(i), "Sconosciuto") for i in ids if i]
            except:
                return []
        
        p['nomi_casa'] = get_nomi(p['titolari_casa'])
        p['nomi_trasferta'] = get_nomi(p['titolari_trasferta'])
        p['nome_squadra_casa'] = nomi_squadre.get(p['squadra_casa_id'], "N/A")
        p['nome_squadra_trasferta'] = nomi_squadre.get(p['squadra_trasferta_id'], "N/A")

    # --- NUOVO CALCOLO DELLA CLASSIFICA DINAMICA ---
    # Inizializziamo il dizionario della classifica per ogni squadra presente
    classifica_dict = {}
    for u in utenti:
        classifica_dict[u['id']] = {
            'nome_squadra': u['nome_squadra'],
            'punti': 0,
            'vinte': 0,
            'pareggiate': 0,
            'perse': 0,
            'goal_fatti': 0
        }

    # Estraiamo tutte le partite dal database per calcolare i punti
    cursor.execute("SELECT * FROM partite")
    tutte_le_partite = cursor.fetchall()

    for p in tutte_le_partite:
        # Calcoliamo le statistiche solo se la partita è terminata (ossia i gol non sono NULL)
        if p['gol_casa'] is not None and p['gol_trasferta'] is not None:
            id_casa = p['squadra_casa_id']
            id_trasferta = p['squadra_trasferta_id']
            g_casa = int(p['gol_casa'])
            g_trasferta = int(p['gol_trasferta'])

            # Aggiorniamo i gol fatti
            if id_casa in classifica_dict:
                classifica_dict[id_casa]['goal_fatti'] += g_casa
            if id_trasferta in classifica_dict:
                classifica_dict[id_trasferta]['goal_fatti'] += g_trasferta

            # Assegnazione punti e statistiche V/P/S
            if g_casa > g_trasferta:
                if id_casa in classifica_dict:
                    classifica_dict[id_casa]['punti'] += 3
                    classifica_dict[id_casa]['vinte'] += 1
                if id_trasferta in classifica_dict:
                    classifica_dict[id_trasferta]['perse'] += 1
            elif g_casa < g_trasferta:
                if id_trasferta in classifica_dict:
                    classifica_dict[id_trasferta]['punti'] += 3
                    classifica_dict[id_trasferta]['vinte'] += 1
                if id_casa in classifica_dict:
                    classifica_dict[id_casa]['perse'] += 1
            else:
                if id_casa in classifica_dict:
                    classifica_dict[id_casa]['punti'] += 1
                    classifica_dict[id_casa]['pareggiate'] += 1
                if id_trasferta in classifica_dict:
                    classifica_dict[id_trasferta]['punti'] += 1
                    classifica_dict[id_trasferta]['pareggiate'] += 1

    # Trasformiamo il dizionario in una lista e la ordiniamo
    # Ordinamento primario: punti (decrescente), ordinamento secondario: gol fatti (decrescente)
    classifica_lista = list(classifica_dict.values())
    classifica_lista.sort(key=lambda x: (x['punti'], x['goal_fatti']), reverse=True)

    cursor.close()
    conn.close()

    # --- NUOVO: MAPPA DEI CALCIATORI SCHIERATI PER OGNI GIORNATA ---
    # Creiamo un dizionario dove per ogni giornata salviamo gli ID dei giocatori titolari
    calciatori_schierati_per_giornata = {}
    
    for p in partite:
        giornata_num = p['giornata']
        if giornata_num not in calciatori_schierati_per_giornata:
            calciatori_schierati_per_giornata[giornata_num] = set()
            
        try:
            ids_casa = json.loads(p['titolari_casa']) if p['titolari_casa'] else []
            ids_trasferta = json.loads(p['titolari_trasferta']) if p['titolari_trasferta'] else []
            
            # Aggiungiamo gli ID al set della giornata corrispondente
            for i in ids_casa:
                if i: calciatori_schierati_per_giornata[giornata_num].add(int(i))
            for i in ids_trasferta:
                if i: calciatori_schierati_per_giornata[giornata_num].add(int(i))
        except:
            pass

    # Trasformiamo i set in liste/dizionari normali per passarli facilmente a Jinja (HTML)
    mappa_schierati_js = {g: list(ids) for g, ids in calciatori_schierati_per_giornata.items()}

    return render_template('admin.html', utenti=utenti, calciatori=calciatori, rose=rose, contatori=contatori, rose_js=json.dumps(rose_per_js), partite=partite, classifica=classifica_lista, schierati=mappa_schierati_js)

import webbrowser
from threading import Timer

#def apri_browser():
    # Sostituisci il numero della porta se la tua app usa una porta diversa da 5000
    #webbrowser.open_new("http://127.0.0.1:5000/")

if __name__ == '__main__':
    # Avvia una funzione parallela che aspetta 1 secondo (dando il tempo a Flask di accendersi) 
    # e poi apre automaticamente la pagina del browser
    #Timer(1, apri_browser).start()
    porta = int(os.environ.get('PORT', 5000))
    
    # Questo è il tuo vecchio avvio (lascia pure i tuoi parametri se ne avevi altri come host o port)
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=porta)
