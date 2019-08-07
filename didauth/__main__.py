from flask import Flask, render_template, flash, request, url_for, redirect, session, jsonify
from passlib.hash import sha256_crypt
from wtforms import Form, TextField, PasswordField, validators

from fastecdsa.encoding.sec1 import SEC1Encoder
from fastecdsa import ecdsa, curve

from urllib import urlencode
from flask_qr import QR

from MySQLdb import connect
from MySQLdb import escape_string as thwart
from functools import wraps

import gc
from random import randint
import json
import os

from dotenv import load_dotenv
load_dotenv(verbose=True)

DEBUG = True
app = Flask(__name__)
qrcode = QR(app)
app.config.from_object(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

class RegistrationForm(Form):
    name = TextField('Name')
    email = TextField('Email Address')
    password = PasswordField('New Password', [
        validators.Required(),
        validators.EqualTo('confirm', message='Passwords must match')
    ])
    confirm = PasswordField('Repeat Password')

def connection():
    conn = connect(host= os.getenv('DB_HOST'),
                           port= int(os.getenv('DB_PORT')),
                           user = os.getenv('DB_USERNAME'),
                           passwd = os.getenv('DB_PASSWORD'),
                           db = os.getenv('DB_DATABASE'))
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS didauth_users (
                    id BIGINT(20) AUTO_INCREMENT PRIMARY KEY, 
                    name VARCHAR(255), 
                    password VARCHAR(255), 
                    email VARCHAR(255), 
                    did VARCHAR(64),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW() ON UPDATE now()
                )'''
            )
    c.execute('''CREATE TABLE IF NOT EXISTS didauth_requests (
                    id BIGINT(20) AUTO_INCREMENT PRIMARY KEY, 
                    state VARCHAR(20), 
                    data json, 
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW() ON UPDATE now()
                )'''
            )
    return c, conn

def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash("You need to login first")
            return redirect(url_for('login'))

    return wrap

@app.route("/checkElaAuth", methods=['GET'])
def check_ela_auth():
    state = session['elaState']
    if not state:
        return jsonify(False), 404
    try:
        c, conn = connection()
        x = c.execute("SELECT data FROM didauth_requests WHERE state = %s AND created_at >= (NOW() - INTERVAL 1 MINUTE)",
                        [state])
        if int(x) == 0:
            return jsonify({'message': 'Token not found'}), 404
        query_result = [ dict(line) for line in [zip([ column[0] for column in c.description], row) for row in c.fetchall()] ][0]
        data = json.loads(query_result['data'])
        session['elaDidInfo'] = data

        x = c.execute("SELECT did FROM didauth_users WHERE did = %s",
                    [thwart(data["DID"])])
        if int(x) == 0:
            redirect = "/register_with_elastos_complete"
            session['redirect_success'] = True
        else:
            redirect = "/account"
            session['logged_in'] = True
            session['name'] = data['Nickname']
            session['email'] = data['Email']
            session['did'] = data['DID']
        conn.commit()  
    except Exception as e:
        return jsonify({'error': str(e)}), 404
    finally:
        if(conn):
            c.close()
            conn.close()
            gc.collect()

    return jsonify({'redirect': redirect})

@app.route("/api/did/callback", methods=['POST'])
def did_callback():
    if request.method == 'POST':
        if not request.json or not 'Data' in request.json:
            abort(400)
        data = request.json['Data']
        data_json = json.loads(data)
        sig = request.json['Sign']
        client_public_key = data_json['PublicKey']

        r, s = int(sig[:64],16), int(sig[64:], 16)
        public_key = SEC1Encoder.decode_public_key(bytearray.fromhex(client_public_key), curve.P256)
        valid = ecdsa.verify((r, s), data, public_key)
        if not valid:
            return jsonify({'message': 'Unauthorized'}), 401
        try:
            c, conn = connection()
            x = c.execute("SELECT data FROM didauth_requests WHERE state = %s AND created_at >= (NOW() - INTERVAL 1 MINUTE)",
                        [thwart(data_json["RandomNumber"])])
            if int(x) == 0:
                return jsonify({'message': 'Unauthorized'}), 401
            auth_data = json.loads(c.fetchone()[0])
            auth_data["auth"] = True
            auth_data = {key: value for (key, value) in (auth_data.items() + data_json.items())}

            c.execute("UPDATE didauth_requests SET data = %s WHERE state = %s",
                        (json.dumps(auth_data), data_json["RandomNumber"]))
            conn.commit()  
        except Exception as e:
            return(str(e))    
        finally:
            if(conn):
                c.close()
                conn.close()
                gc.collect()                  
    return jsonify({'result': True}), 201

@app.route("/", methods=['GET', 'POST'])
def home():
    try:
        form = RegistrationForm(request.form)

        if request.method == 'POST' and form.validate():
            name = form.name.data
            email = form.email.data
            password = sha256_crypt.encrypt((str(form.password.data)))
            c, conn = connection()

            x = c.execute("SELECT * FROM didauth_users WHERE name = %s",
                          [thwart(name)])

            if int(x) > 0:
                flash("That name is already taken, please choose another")
                return render_template('index.html', form=form)
            else:
                c.execute("INSERT INTO didauth_users (name, password, email) VALUES (%s, %s, %s)",
                          (thwart(name), thwart(password), thwart(email)))               
                conn.commit()
                c.close()
                conn.close()
                gc.collect()
                flash("Thanks for registering!")
                
                session['logged_in'] = True
                session['name'] = name
                session['email'] = email
                session['did'] = 'None'

                return redirect(url_for('account'))
        return render_template("index.html", form=form)
    except Exception as e:
        return(str(e))            

@app.route("/register_with_elastos_complete", methods=['GET', 'POST'])
def register_with_elastos_complete():
    error = ''
    try:
        if 'redirect_success' not in session.keys():
            return redirect(url_for('home'))
        if request.method == 'POST':
            name = request.form['name']
            email = request.form['email']
            did = request.form['did']
            c, conn = connection()

            x = c.execute("SELECT * FROM didauth_users WHERE name = %s",
                          [thwart(name)])

            if int(x) > 0:
                flash("That name is already taken, please choose another")
                return render_template('register_with_elastos_complete.html', error=error)
            else:
                c.execute("INSERT INTO didauth_users (name, email, did) VALUES (%s, %s, %s)",
                          (thwart(name), thwart(email), thwart(did)))
                
                conn.commit()
                c.close()
                conn.close()
                gc.collect()
                flash("Thanks for registering!")
                
                session['logged_in'] = True
                session['name'] = name
                session['email'] = email
                session['did'] = did
                session.pop('elaDidInfo')

                return redirect(url_for('account'))
        return render_template("register_with_elastos_complete.html", error=error)
    except Exception as e:
        return(str(e))     

@app.route("/register_with_elastos", methods=['GET'])
def register_with_elastos(): 
    public_key = os.getenv('ELA_PUBLIC_KEY')
    did = os.getenv('ELA_DID')
    app_id = os.getenv('ELA_APP_ID')
    app_name = os.getenv('ELA_APP_NAME')

    random = randint(10000000000,999999999999)
    session['elaState'] = random

    url_params = {
        'CallbackUrl': os.getenv('APP_URL') + '/api/did/callback',
        'Description': 'Elastos DID Authentication',
        'AppID': app_id,
        'PublicKey': public_key,
        'DID': did,
        'RandomNumber': random,
        'AppName': app_name,
        'RequestInfo': 'Nickname,Email'
    }

    url = 'elaphant://identity?' + urlencode(url_params)

    # Save token to the database didauth_requests
    token = { 'state': random, 'data': { 'auth': False }}
    try:
        c, conn = connection()
        c.execute("INSERT INTO didauth_requests (state, data) VALUES (%s, %s)",
                          (token['state'], json.dumps(token['data'])))
                          
        # Purge old requests for housekeeping. If the time denoted by 'created_by' 
        # is more than 2 minutes old, delete the row
        c.execute("DELETE FROM didauth_requests WHERE created_at < (NOW() - INTERVAL 2 MINUTE)")      
        
        conn.commit()
    except Exception as e:
        return(str(e))
    finally:
        if(conn):
            c.close()
            conn.close()
            gc.collect()

    # Load the QR view, show the code and auth instructions
    session['elephant_url'] =  qrcode.qrFor(url, dimension=400)
    return render_template("register_with_elastos.html")

@app.route('/login', methods=["GET","POST"])
def login():
    error = ''
    try:
        c, conn = connection()
        if request.method == "POST":
            x = c.execute("SELECT * FROM didauth_users WHERE name = %s AND did is NULL",
                          [thwart(request.form['name'])])
            if int(x) == 0:
                error = "This user is registered using DID. Please 'Login with Elastos' instead"
                return render_template("login.html", error = error)  
            data = [ dict(line) for line in [zip([ column[0] for column in c.description], row) for row in c.fetchall()] ][0]

            if sha256_crypt.verify(request.form['password'], data['password']):
                session['logged_in'] = True
                session['name'] = data['name']
                session['email'] = data['email']
                session['did'] = data['did']

                flash("You are now logged in")
                return redirect(url_for("account"))
            else:
                error = "Invalid credentials, try again."
        return render_template("login.html", error=error)
    except Exception as e:
        error = "Invalid credentials, try again."
        return render_template("login.html", error = error)  
    finally:
        if(conn):
            c.close()
            conn.close()
            gc.collect() 

@app.route("/login_with_elastos", methods=['GET', 'POST'])
def login_with_elastos():
    return redirect(url_for('register_with_elastos'))

@app.route("/account")
@login_required
def account():
    return render_template("account.html")

@app.route("/logout/")
@login_required
def logout():
    session.clear()
    flash("You have been logged out!")
    gc.collect()
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(host='0.0.0.0')
