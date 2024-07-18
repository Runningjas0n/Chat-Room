from flask import Flask, render_template, request, jsonify, redirect
from flask_socketio import SocketIO, send
import sqlite3
import requests
import os
from werkzeug.utils import secure_filename
from flask import send_file

app = Flask(__name__)
socketio = SocketIO(app)

# 在本地运行的IP地址和端口（可以在局域网中访问）
host_ip = '0.0.0.0'
local_port = 5000

# 在公共网络中运行的IP地址和端口（使用80端口）
public_ip = 'https://dd92-183-211-156-202.ngrok-free.app/'
public_port = 80

# ChatGPT API URL
gpt_api_url = 'https://api.openai.com/v1/chat/completions'

# ChatGPT API 密钥，请将其设置为有效的 ChatGPT API 密钥
gpt_api_key = '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'

# 连接到SQLite数据库
conn = sqlite3.connect('chat.db', check_same_thread=False)
cursor = conn.cursor()

# 创建用户表格，用于存储用户信息
cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, email TEXT)')

# 创建messages表格，用于存储聊天记录
cursor.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, message TEXT, color TEXT)')
# 创建articles表格，用于存储文章
cursor.execute('CREATE TABLE IF NOT EXISTS articles (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, content TEXT)')

# 处理用户注册请求
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')

        # 检查用户名是否已存在
        cursor.execute('SELECT * FROM users WHERE username=?', (username,))
        existing_user = cursor.fetchone()
        if existing_user:
            return jsonify({'message': 'Username already exists'}), 400

        # 将新用户信息插入数据库
        cursor.execute('INSERT INTO users (username, password, email) VALUES (?, ?, ?)', (username, password, email))
        conn.commit()

        return jsonify({'message': 'User registered successfully'}), 200

    else:
        return render_template('register.html')

# 添加一个路由来处理登录请求
@app.route('/login', methods=['GET'])
def login():
    # 渲染登录页面模板
    return render_template('login.html')

    # 查询数据库，验证用户提供的用户名和密码是否匹配注册过的信息
    cursor.execute('SELECT * FROM users WHERE username=? AND password=?', (username, password))
    user = cursor.fetchone()

    if user:
        # 如果用户验证通过，将用户存入会话中
        session['username'] = username
        return redirect('/chat_with_gpt_page')
    else:
        # 如果验证失败，重定向回登录页面或返回错误信息给用户
        return redirect('/login')  # 这里可以重定向回登录页面，或者返回错误信息给用户

UPLOAD_FOLDER = 'uploads'  # 上传文件存储路径
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html', server_ip=public_ip, server_port=public_port)

@app.route('/chat_with_gpt_page', methods=['GET'])
def chat_with_gpt_page():
    return render_template('chatgpt.html')

@app.route('/chat_with_gpt', methods=['POST'])
def chat_with_gpt_api():
    try:
        data = request.get_json()
        user_message = data['message']
        print("User message:", user_message)  # 输出用户发送的消息
        gpt_response = get_gpt_response(user_message)
        print("GPT response:", gpt_response)  # 输出从 ChatGPT API 收到的响应
        
        # 保存用户与ChatGPT的聊天记录到数据库
        cursor.execute('INSERT INTO messages (username, message, color) VALUES (?, ?, ?)', ('User', user_message, '#000000'))
        cursor.execute('INSERT INTO messages (username, message, color) VALUES (?, ?, ?)', ('ChatGPT', gpt_response, '#000000'))
        conn.commit()
        
        return jsonify({'message': gpt_response})

    except Exception as e:
        print("Error:", e)  # 输出错误信息
        return jsonify({'error': str(e)})

def get_gpt_response(user_message):
    try:
        payload = {
            'model': 'gpt-3.5-turbo',
            'messages': [{'role': 'system', 'content': 'You are a helpful assistant.'}, {'role': 'user', 'content': user_message}]
        }
        response = requests.post(gpt_api_url, json=payload, headers={'Authorization': f'Bearer {gpt_api_key}'})
        response_data = response.json()
        print("Response data:", response_data)  # 调试输出
        gpt_response = response_data['choices'][0]['message']['content']
        return gpt_response

    except Exception as e:
        return str(e)



@socketio.on('message')
def handle_message(data):
    print('Received message:', data)
    # 保存消息到数据库
    cursor.execute('INSERT INTO messages (username, message, color) VALUES (?, ?, ?)', (data['username'], data['message'], data['color']))
    conn.commit()
    # 广播消息到聊天室中的所有用户
    if 'image' in data:
        # 如果消息中包含图片链接，则广播给所有客户端
        socketio.emit('message', {'username': data['username'], 'image': data['image']})
    else:
        # 如果消息中不包含图片链接，则广播消息内容给所有客户端
        socketio.emit('message', data)
@app.route('/get_messages', methods=['GET'])
def get_messages():
    cursor.execute('SELECT * FROM messages')
    messages = cursor.fetchall()
    messages_dict = [{'username': msg[1], 'message': msg[2], 'color': msg[3]} for msg in messages]
    return jsonify(messages_dict)

@app.route('/get_chat_history', methods=['GET'])
def get_chat_history():
    cursor.execute('SELECT * FROM messages')
    messages = cursor.fetchall()
    chat_history = [{'username': msg[1], 'message': msg[2], 'color': msg[3]} for msg in messages]
    return jsonify(chat_history)

@app.route('/get_users', methods=['GET'])
def get_users():
    users = [namespace.connected[request.sid]['username'] for namespace in socketio.server.namespace_handlers.values() if request.sid in namespace.connected]
    return jsonify(users)

@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'})
    
    image = request.files['image']
    if image.filename == '':
        return jsonify({'error': 'No selected image'})
    
    if image and allowed_file(image.filename):
        filename = secure_filename(image.filename)
        image_path = os.path.join(UPLOAD_FOLDER, filename)
        image.save(image_path)
        # 生成下载链接
        download_link = f"/download/{filename}"
        return jsonify({'imageUrl': image_path, 'downloadLink': download_link})
    else:
        return jsonify({'error': 'Invalid image file'})

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

@app.route('/diary')
def diary():
    return render_template('Diary.html')

@app.route('/read')
def read():
    cursor.execute('SELECT * FROM articles')
    articles = cursor.fetchall()
    return render_template('read.html', articles=articles)

@app.route('/download/<path:filename>', methods=['GET'])
def download_file(filename):
    try:
        return send_file(f'uploads/{filename}', as_attachment=True)
    except Exception as e:
        return str(e), 404

@app.route('/upload_article', methods=['POST'])
def submit_article():
    title = request.form.get('title')
    content = request.form.get('content')
    cursor.execute('INSERT INTO articles (title, content) VALUES (?, ?)', (title, content))
    conn.commit()
    return redirect('/')  # 重定向到index.html页面

if __name__ == "__main__":
    socketio.run(app, host=host_ip, port=local_port)
