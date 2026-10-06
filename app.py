from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
import os
import random
import time
from datetime import datetime

# --- Fallback for Termux (Real data only works on Render) ---
try:
    import yfinance as yf
    import pandas_ta_classic as ta
    REAL_DATA = True
except ImportError:
    REAL_DATA = False

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'koechian-secret-key-12345'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///koechian.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    balance = db.Column(db.Float, default=1000.0)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- MOCK DATA FOR TERMUX ---
mock_base_price = 1.0850

def get_mock_ohlc():
    global mock_base_price
    data = []
    base_price = mock_base_price
    now = datetime.now()
    for i in range(100):
        time_unix = int((now.timestamp()) - ((100-i) * 60)) # 1 min intervals
        change = random.uniform(-0.003, 0.003)
        open_p = base_price
        close_p = base_price + change
        high_p = max(open_p, close_p) + random.uniform(0, 0.001)
        low_p = min(open_p, close_p) - random.uniform(0, 0.001)
        data.append({"time": time_unix, "open": open_p, "high": high_p, "low": low_p, "close": close_p})
        base_price = close_p
    mock_base_price = base_price
    return data

# --- ROUTES ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Username or Email already exists!', 'error')
            return redirect(url_for('register'))
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, email=email, password_hash=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('index.html', auth_view='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'error')
            return redirect(url_for('login'))
    return render_template('index.html', auth_view='login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    return render_template('index.html', auth_view='dashboard', user=current_user)

@app.route('/api/ohlc')
def ohlc():
    if REAL_DATA:
        df = yf.download("EURUSD=X", interval="1m", period="1d")
        df = df.reset_index()
        df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
        df['time'] = df['time'].astype('int64') // 10**9
        return jsonify(df[['time', 'open', 'high', 'low', 'close']].to_dict('records'))
    else:
        return jsonify(get_mock_ohlc())

@app.route('/api/live_tick')
def live_tick():
    if REAL_DATA:
        df = yf.download("EURUSD=X", interval="1m", period="1d")
        df = df.reset_index()
        df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
        df['time'] = df['time'].astype('int64') // 10**9
        return jsonify(df.iloc[-1].to_dict())
    else:
        global mock_base_price
        change = random.uniform(-0.001, 0.001)
        new_price = mock_base_price + change
        now = int(time.time())
        candle = {
            "time": now,
            "open": mock_base_price,
            "high": max(mock_base_price, new_price),
            "low": min(mock_base_price, new_price),
            "close": new_price
        }
        mock_base_price = new_price
        return jsonify(candle)

@app.route('/api/signal')
def signal():
    if not REAL_DATA:
        rsi = random.uniform(20, 80)
        sig = "BUY" if rsi < 35 else ("SELL" if rsi > 65 else "HOLD")
        return jsonify({"signal": sig, "rsi": round(rsi, 2)})
    df = yf.download("EURUSD=X", interval="1m", period="1d")
    df['RSI'] = ta.rsi(df['close'], length=14)
    last = df.iloc[-1]
    sig = "HOLD"
    if last['RSI'] < 35: sig = "BUY"
    elif last['RSI'] > 65: sig = "SELL"
    return jsonify({"signal": sig, "rsi": round(last['RSI'], 2)})

@app.route('/api/deposit', methods=['POST'])
@login_required
def deposit():
    amount = float(request.json.get('amount', 10))
    current_user.balance += amount
    db.session.commit()
    return jsonify({"status": "success", "message": f"Deposit of ${amount} successful! New balance: ${current_user.balance}"})

@app.route('/api/withdraw', methods=['POST'])
@login_required
def withdraw():
    amount = float(request.json.get('amount', 10))
    if amount > current_user.balance:
        return jsonify({"status": "error", "message": "Insufficient funds!"})
    current_user.balance -= amount
    db.session.commit()
    return jsonify({"status": "success", "message": f"Withdrawal of ${amount} initiated. New balance: ${current_user.balance}"})

python
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
