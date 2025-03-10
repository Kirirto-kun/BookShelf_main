from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import firebase_admin
from firebase_admin import credentials, firestore, storage
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from werkzeug.utils import secure_filename
from flask_cors import CORS

# Инициализация Firebase
cred = credentials.Certificate('bs-hack1-firebase-adminsdk-glq41-35fd486e64.json')  # Замените на путь к вашему JSON-файлу
firebase_admin.initialize_app(cred, {
    'storageBucket': 'bs-hack1.appspot.com'  # Замените на имя вашего бакета
})
db = firestore.client()
bucket = storage.bucket()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

CORS(app)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
@app.route("/index")
@login_required
def index():
    user_id = session['user_id']

    # Получаем все посты
    posts_ref = db.collection('posts')
    posts = posts_ref.stream()
    posts_list = []

    for post in posts:
        post_data = post.to_dict()
        post_data['id'] = post.id
        post_data['created_at_str'] = post_data['created_at'].strftime('%Y-%m-%d %H:%M:%S') if post_data.get('created_at') else '2024-09-07 09:18:13'
        posts_list.append(post_data)

    # Получаем лайки текущего пользователя
    likes_ref = db.collection('likes').where('user_id', '==', user_id)
    likes = likes_ref.stream()
    liked_post_ids = [like.to_dict()['post_id'] for like in likes]

    return render_template('index.html', posts=posts_list, liked_posts=liked_post_ids)


@app.route("/create_event", methods=["GET", "POST"])
@login_required
def create_event():
    if request.method == "POST":
        # Получаем данные из формы
        event_name = request.form.get("event_name")
        location = request.form.get("location")
        colour = request.form.get("colour")
        description = request.form.get("description")
        date = request.form.get("date")
        time = request.form.get("time")
        
        # Создаем документ в коллекции 'events'
        events_ref = db.collection('events')
        events_ref.add({
            'event_name': event_name,
            'location': location,
            'colour': colour,
            'description': description,
            'date': date,
            'time': time
        })

        flash("Event created successfully!")
        return redirect(url_for('calendar'))
    
    return render_template('create_event.html')

@app.route("/calendar")
@login_required
def calendar():
    # Получаем все события
    events_ref = db.collection('events')
    events = events_ref.stream()
    events_list = []

    for event in events:
        event_data = event.to_dict()
        event_data['id'] = event.id
        events_list.append(event_data)

    return render_template('calendar.html', events=events_list)
@app.route("/users")
@login_required
def get_users():
    try:
        users_ref = db.collection('users')
        users = [user.to_dict() for user in users_ref.stream()]
        return jsonify(users)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/search_users', methods=['GET'])
def search_users():
    username = request.args.get('username')
    if not username:
        return jsonify([])  # Возвращаем пустой список при отсутствии имени пользователя

    users = db.collection('users').where('username', '==', username).get()
    user_list = [{'userId': user.id, 'username': user.to_dict()['username']} for user in users]

    return jsonify(user_list)


@app.route("/messages/<user_id>")
@login_required
def get_messages(user_id):
    try:
        current_user_id = session.get('user_id', '')
        messages_ref = db.collection('messages').document(current_user_id).collection('chats').document(user_id)
        messages = [msg.to_dict() for msg in messages_ref.collection('messages').stream()]
        return jsonify(messages)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/send_message", methods=['POST'])
@login_required
def send_message():
    try:
        data = request.json
        from_user = session.get('user_id', '')
        to_user = data['to_user']
        message_text = data['message']

        # Сохранение сообщения с временной меткой в обеих коллекциях чатов
        messages_ref = db.collection('messages').document(from_user).collection('chats').document(to_user)
        messages_ref.collection('messages').add({
            'from_user': from_user,
            'message': message_text,
            'timestamp': firestore.SERVER_TIMESTAMP  # Добавляем время отправки
        })

        messages_ref = db.collection('messages').document(to_user).collection('chats').document(from_user)
        messages_ref.collection('messages').add({
            'from_user': from_user,
            'message': message_text,
            'timestamp': firestore.SERVER_TIMESTAMP  # Добавляем время отправки
        })

        return jsonify({'status': 'Message sent successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/messages")
@login_required
def messages_page():
    return render_template('messages.html')

@app.route('/liked_posts')
@login_required
def liked_posts():
    user_id = session['user_id']
    
    # Fetch the IDs of posts that the user has liked
    liked_posts_ref = db.collection('likes').where('user_id', '==', user_id).stream()
    liked_post_ids = [doc.to_dict()['post_id'] for doc in liked_posts_ref]
    
    # Fetch the post data based on the IDs
    posts_list = []
    for post_id in liked_post_ids:
        post_ref = db.collection('posts').document(post_id).get()
        if post_ref.exists:
            post_data = post_ref.to_dict()
            post_data['id'] = post_ref.id
            post_data['created_at_str'] = post_data['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            posts_list.append(post_data)
    
    return render_template('liked_posts.html', posts=posts_list)




@app.route("/about")
@login_required
def about():
    return render_template('about.html')

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        title = request.form['title']
        text = request.form['text']
        userId = session['user_id']
        username = session['username']
        image = request.files.get('image')
        image_url = None

        if image:
            filename = secure_filename(image.filename)
            blob = bucket.blob(filename)
            blob.upload_from_file(image, content_type=image.content_type)
            blob.make_public()
            image_url = blob.public_url

        # Генерируем ID поста вручную
        post_id = db.collection('posts').document().id

        # Добавляем новый пост в Firestore с определенным ID и временем создания
        db.collection('posts').document(post_id).set({
            'title': title,
            'text': text,
            'userId': userId,
            'image_url': image_url,
            'username': username,
            'post_id': post_id,  # Сохраняем ID документа в самом документе
            'created_at': firestore.SERVER_TIMESTAMP  # Добавляем время создания
        })

        return redirect('/create')

    # Получаем все посты для текущего пользователя
    user_posts_ref = db.collection('posts').where('userId', '==', session['user_id']).stream()
    posts_list = []
    for post in user_posts_ref:
        post_data = post.to_dict()
        post_data['id'] = post.id  # Добавляем ID документа в данные поста
        # Преобразуем Firestore Timestamp в строку
        post_data['created_at_str'] = post_data['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        posts_list.append(post_data)

    return render_template('create.html', posts=posts_list)


@app.route('/delete/<post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    # Удаляем пост из Firestore
    post_ref = db.collection('posts').document(post_id)
    post = post_ref.get()
    
    if post.exists:
        post_data = post.to_dict()
        
        # Удаляем изображение из Google Cloud Storage, если оно есть
        if post_data.get('image_url'):
            filename = post_data['image_url'].split('/')[-1]
            blob = bucket.blob(filename)
            blob.delete()
        
        # Удаляем пост из коллекции
        post_ref.delete()

    return redirect('/create')


@app.route('/toggle_like/<post_id>', methods=['POST'])
@login_required
def toggle_like(post_id):
    user_id = session['user_id']
    
    # Проверяем, поставил ли пользователь лайк этому посту
    like_ref = db.collection('likes').where('post_id', '==', post_id).where('user_id', '==', user_id).stream()
    liked = any(like_ref)  # Если есть результат, значит лайк уже был
    
    post_ref = db.collection('posts').document(post_id)
    
    if liked:
        # Если лайк уже поставлен, удаляем его
        for doc in like_ref:
            db.collection('likes').document(doc.id).delete()
        
        # Уменьшаем количество лайков на 1
        post_ref.update({
            'likes_count': firestore.Increment(-1)
        })
    else:
        # Если лайк не поставлен, добавляем его
        db.collection('likes').add({
            'post_id': post_id,
            'user_id': user_id
        })

        # Увеличиваем количество лайков на 1
        post_ref.update({
            'likes_count': firestore.Increment(1)
        })
    
    return redirect(url_for('index'))

@app.route('/like/<post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    user_id = session['user_id']
    
    # Проверяем, поставил ли пользователь лайк
    like_ref = db.collection('likes').where('post_id', '==', post_id).where('user_id', '==', user_id).limit(1)
    existing_like = list(like_ref.stream())

    post_ref = db.collection('posts').document(post_id)

    if existing_like:
        # Если лайк уже есть, удаляем его и уменьшаем счетчик лайков
        existing_like[0].reference.delete()
        post_ref.update({
            'likes_count': firestore.Increment(-1)
        })
    else:
        # Если лайка нет, добавляем его и увеличиваем счетчик лайков
        db.collection('likes').add({
            'post_id': post_id,
            'user_id': user_id
        })
        post_ref.update({
            'likes_count': firestore.Increment(1)
        })

    return redirect(url_for('index'))



@app.route('/comments/<post_id>', methods=['GET', 'POST'])
@login_required
def comments(post_id):
    # Логирование для отладки
    print(f"Fetching comments for post ID: {post_id}")

    # Ищем пост по ID
    post_ref = db.collection('posts').document(post_id)
    post = post_ref.get()

    if not post.exists:
        flash('Post not found', 'error')
        return redirect('/index')

    post_data = post.to_dict()

    if request.method == 'POST':
        comment_text = request.form['comment_text']
        author = session['username']  # Используем имя пользователя из сессии

        # Логирование для отладки
        print(f"Adding comment by {author}: {comment_text}")

        # Добавляем комментарий в подколлекцию 'comments' под постом
        post_ref.collection('comments').add({
            'text': comment_text,
            'author': author,  # Сохраняем имя пользователя как автора
            'timestamp': firestore.SERVER_TIMESTAMP
        })

        flash('Comment added successfully', 'success')
        return redirect(url_for('comments', post_id=post_id))

    # Получаем все комментарии для этого поста, отсортированные по времени
    comments_ref = post_ref.collection('comments').order_by('timestamp').stream()
    comments_list = [comment.to_dict() for comment in comments_ref]

    return render_template('comments.html', post=post_data, comments=comments_list, post_id=post_id)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Parse JSON data
        data = request.get_json()

        full_name = data['full_name']
        email = data['email']
        username = data['username']
        password = data['password']
        pfp_url = data.get('pfp_url', '')
        rank = data.get('rank', 'Newbie')

        hashed_password = generate_password_hash(password)

        # Create a new document with a unique ID
        user_ref = db.collection('users').document()
        user_data = {
            'id': 'ylROSeQ4bFokOQV8hRJG',  # This should ideally be user_ref.id, but you use a fixed ID here
            'full_name': full_name,
            'rank': rank,
            'pfp_url': pfp_url,
            'email': email,
            'username': username,
            'password': hashed_password,
            'userId': user_ref.id,
            'number_of_participations': 0,
            'number_of_creations': 0,
            'points': 0,
            'creations': [
                {
                    'createdAt': None,  # Replace with actual timestamp when available
                    'event_id': None,   # Replace with actual event ID when available
                }
            ],
            'participation': [
                {
                    'visitedAt': None,  # Replace with actual timestamp when available
                    'event_id': None,   # Replace with actual event ID when available
                }
            ],
            'recommend': {
                "Развлечения": 0.16,
                "Образование и мастер-классы": 0.16,
                "Музыка и концерты": 0.16,
                "Еда и напитки": 0.16,
                "Ярмарки и выставки": 0.16,
                "Кино и театр": 0.16
            }
        }

        # Save user data to Firestore
        user_ref.set(user_data)

        # Store userId and username in session
        session['user_id'] = user_ref.id
        session['username'] = username

        return redirect('/index')
    
    return render_template('register.html')


from flask import request, jsonify

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Retrieve data from JSON
        data = request.get_json()

        username = data.get('email')
        password = data.get('password')

        if not username or not password:
            return jsonify({'error': 'Missing username or password'}), 400

        # Fetch user from Firestore
        users_ref = db.collection('users').where('username', '==', username).limit(1).get()
        if users_ref:
            user_doc = users_ref[0]
            user_data = user_doc.to_dict()

            # Check if the password matches
            if check_password_hash(user_data['password'], password):
                # Store userId and username in session
                session['user_id'] = user_data['userId']
                print(user_data['userId'])
                session['username'] = username
                return jsonify({'redirect': '/index'})
            else:
                return jsonify({'error': 'Invalid credentials'}), 401
        else:
            return jsonify({'error': 'User not found'}), 404

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect('/login')



@app.route('/create_community', methods=['GET', 'POST'])
@login_required
def create_community():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        user_id = session['user_id']
        username = session['username']
        
        # Create a new community document with a unique ID
        community_ref = db.collection('communities').document()  # Auto-generate a unique ID
        community_id = community_ref.id
        community_ref.set({
            'id': community_id,  # Explicitly add the community ID field
            'name': name,
            'description': description,
            'members': [user_id]
        })

        # Add the community ID to the user's list
        db.collection('users').document(user_id).collection('communities').add({
            'community_id': community_id,
            'username': username
        })
        
        return redirect(url_for('communities'))
    
    return render_template('create_community.html')


@app.route('/join_community/<community_id>', methods=['POST'])
@login_required
def join_community(community_id):
    user_id = session['user_id']
    username = session['username']
    
    # Add user to the community
    community_ref = db.collection('communities').document(community_id)
    community_ref.update({
        'members': firestore.ArrayUnion([user_id])
    })

    # Add the community to the user's list
    db.collection('users').document(user_id).collection('communities').add({
        'community_id': community_id,
        'username': username
    })
    
    return redirect(url_for('communities'))


@app.route('/communities')
@login_required
def communities():
    user_id = session['user_id']
    
    communities_ref = db.collection('communities').stream()
    communities_list = [community.to_dict() for community in communities_ref]

    user_communities_ref = db.collection('users').document(user_id).collection('communities').stream()
    user_communities = [doc.to_dict()['community_id'] for doc in user_communities_ref]

    return render_template('communities.html', communities=communities_list, user_communities=user_communities)







@app.route('/community_chat/<community_id>', methods=['GET', 'POST'])
@login_required
def community_chat(community_id):
    user_id = session['user_id']
    
    # Fetch community members
    community_ref = db.collection('communities').document(community_id).get()
    community_data = community_ref.to_dict()
    member_ids = community_data.get('members', [])
    
    # Check if the user is a member
    is_member = user_id in member_ids
    
    if request.method == 'POST':
        if is_member:
            message = request.form['message']
            username = session['username']
            
            # Add the message to the chat
            db.collection('communities').document(community_id).collection('chat').add({
                'user_id': user_id,
                'username': username,
                'message': message,
                'timestamp': firestore.SERVER_TIMESTAMP
            })
        else:
            flash("You must be a member of the community to post messages.", "warning")
        
        return redirect(url_for('community_chat', community_id=community_id))
    
    # Fetch chat messages
    chat_ref = db.collection('communities').document(community_id).collection('chat').order_by('timestamp').stream()
    chat_messages = [msg.to_dict() for msg in chat_ref]

    # Fetch community members
    members = []
    for member_id in member_ids:
        user_ref = db.collection('users').document(member_id).get()
        user_data = user_ref.to_dict()
        members.append({
            'username': user_data.get('username', 'Unknown User')
        })

    return render_template('community_chat.html', community_id=community_id, chat_messages=chat_messages, community_members=members, is_member=is_member)


@app.route('/leave_community/<community_id>', methods=['POST'])
@login_required
def leave_community(community_id):
    user_id = session['user_id']
    
    # Remove user from the community
    community_ref = db.collection('communities').document(community_id)
    community_ref.update({
        'members': firestore.ArrayRemove([user_id])
    })

    # Remove the community from the user's list
    user_communities_ref = db.collection('users').document(user_id).collection('communities').where('community_id', '==', community_id).stream()
    for doc in user_communities_ref:
        doc.reference.delete()

    return redirect(url_for('communities'))


@app.route('/add_events', methods=['POST'])
def add_events():
    # Получаем список событий из тела запроса
    events = request.json.get('events', [])
    
    # Проверяем, что список не пустой
    if not events:
        return jsonify({"success": False, "message": "Список событий пустой!"}), 400

    # Ссылка на коллекцию
    event_ref = db.collection('events_main')

    # Добавляем события в Firestore
    for event in events:
        event_ref.add(event)

    return jsonify({"success": True, "message": f"Добавлено {len(events)} событий."}), 200




@app.route('/like_event/<category>', methods=['POST'])
def like_category(category):
    user_id = 'bOEYgRcegotVmGQx0pJR'

    user_ref = db.collection('users').document(user_id)
    user = user_ref.get()

    if not user.exists:
        return {'error': 'User not found'}, 404

    user_data = user.to_dict()
    recommend = user_data.get('recommend', {})
    
    if category not in recommend:
        return {'error': 'Category not found'}, 400

    # Изменение значений категорий
    increment_value = 0.05
    decrement_value = increment_value / (len(recommend) - 1)
    
    for cat in recommend:
        if cat == category:
            recommend[cat] += increment_value
        else:
            recommend[cat] -= decrement_value

        # Ограничиваем значения в пределах [0, 1]
        recommend[cat] = max(0, min(1, recommend[cat]))

    user_ref.update({'recommend': recommend})
    
    return {'message': f'Liked category {category}', 'recommend': recommend}

@app.route('/dislike_event/<category>', methods=['POST'])
def dislike_category(category):
    user_id = 'bOEYgRcegotVmGQx0pJR'

    user_ref = db.collection('users').document(user_id)
    user = user_ref.get()

    if not user.exists:
        return {'error': 'User not found'}, 404

    user_data = user.to_dict()
    recommend = user_data.get('recommend', {})
    
    if category not in recommend:
        return {'error': 'Category not found'}, 400

    # Изменение значений категорий
    decrement_value = 0.05
    increment_value = decrement_value / (len(recommend) - 1)
    
    for cat in recommend:
        if cat == category:
            recommend[cat] -= decrement_value
        else:
            recommend[cat] += increment_value

        # Ограничиваем значения в пределах [0, 1]
        recommend[cat] = max(0, min(1, recommend[cat]))

    user_ref.update({'recommend': recommend})
    
    return {'message': f'Disliked category {category}', 'recommend': recommend}




import random

@app.route('/recommend_events', methods=['GET'])
def recommend_events():
    user_id = 'bOEYgRcegotVmGQx0pJR'


    # Получаем данные пользователя
    user_ref = db.collection('users').document(user_id)
    user = user_ref.get()

    if not user.exists:
        return {'error': 'User not found'}, 404

    user_data = user.to_dict()
    recommend = user_data.get('recommend', {})

    if not recommend:
        return {'error': 'No preferences found for user'}, 400

    # Сортируем категории по убыванию предпочтений
    sorted_categories = sorted(recommend.items(), key=lambda x: x[1], reverse=True)
    top_categories = [category for category, _ in sorted_categories]

    # Получаем все события
    events_ref = db.collection('events_main')
    all_events = events_ref.stream()

    # Фильтруем события по категориям
    events_by_category = {category: [] for category in top_categories}
    all_categories = set()  # Список всех категорий, встречающихся в событиях
    for event in all_events:
        event_data = event.to_dict()
        category = event_data.get('category')

        if category in events_by_category:
            events_by_category[category].append(event_data)
        all_categories.add(category)

    # Собираем 5 случайных событий с предпочтением на топовые категории
    recommended_events = []
    # Сначала добавляем события из топовых категорий
    for category in top_categories:
        if len(recommended_events) >= 5:
            break

        category_events = events_by_category[category]
        if category_events:
            random.shuffle(category_events)  # Перемешиваем события категории
            recommended_events.extend(category_events[:5 - len(recommended_events)])  # Добавляем до 5 событий

    # Если осталось место, добавляем случайные события из других категорий
    if len(recommended_events) < 5:
        remaining_categories = list(all_categories - set(top_categories))
        random.shuffle(remaining_categories)  # Перемешиваем остальные категории
        for category in remaining_categories:
            if len(recommended_events) >= 5:
                break
            category_events = events_by_category.get(category, [])
            random.shuffle(category_events)  # Перемешиваем события категории
            recommended_events.extend(category_events[:5 - len(recommended_events)])  # Добавляем до 5 событий

    return {'recommended_events': recommended_events}




from datetime import datetime, timedelta
from flask import request, jsonify
import random

@app.route('/event-by-time', methods=['POST'])
def event_by_time():
    # Получаем дату из запроса
    data = request.get_json()
    if 'date' not in data:
        return jsonify({'error': 'Date is required'}), 400

    # Преобразуем строку в объект datetime
    try:
        base_date = datetime.strptime(data['date'], "%d.%m.%Y")
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use DD.MM.YYYY'}), 400

    # Вычисляем диапазон дат: от 5 до 12 декабря
    start_date = base_date - timedelta(days=7)  # 7 дней назад
    end_date = base_date  # до заданной даты

    # Получаем события из базы данных
    events_ref = db.collection('events_main')
    all_events = events_ref.stream()

    # Фильтруем события по дате
    filtered_events = []
    for event in all_events:
        event_data = event.to_dict()
        event_date_str = event_data.get('date')
        try:
            event_date = datetime.strptime(event_date_str, "%d.%m.%Y")
        except ValueError:
            continue  # Пропускаем событие, если дата невалидна

        # Проверяем, попадает ли событие в нужный диапазон
        if start_date <= event_date <= end_date:
            filtered_events.append(event_data)

    # Сортируем события по дате
    filtered_events.sort(key=lambda x: datetime.strptime(x['date'], "%d.%m.%Y"))

    # Ограничиваем количество событий до 5
    recommended_events = filtered_events[:5]

    return jsonify({'events': recommended_events})

@app.route('/user/me', methods=['GET'])
def get_my_info():
    users_ref = db.collection('users')

    user_doc = users_ref.document('bOEYgRcegotVmGQx0pJR').get()

    if user_doc.exists:
        # If the user is found, return user data
        return jsonify(user_doc.to_dict()), 200
    else:
        # If user doesn't exist
        return jsonify({"error": "User not found"}), 404

@app.route('/events', methods=['GET'])
def all_events_sorted_by_category():
    events_ref = db.collection('events_main')
    all_events = events_ref.stream()
    
    categorized_events = {}
    for event in all_events:
        event_dict = event.to_dict()
        event_dict['id'] = event.id
        category = event_dict.get('category', 'Uncategorized')  # Default category if none is set
        if category not in categorized_events:
            categorized_events[category] = []
        categorized_events[category].append(event_dict)
    
    return jsonify(categorized_events), 200


import requests
from flask import request, jsonify
import json
# Константы для подключения к Azure OpenAI
AZURE_API_URL = "https://ai-jafarman20072174ai473877890883.cognitiveservices.azure.com/openai/deployments/gpt-4o-2/chat/completions?api-version=2024-08-01-preview"
AZURE_API_KEY = "AS6k4TYveS8ZScDAFA7KBZ9Wbibno6ffOg2SBzzQYoHLLRVTQ5C0JQQJ99AJACYeBjFXJ3w3AAAAACOGNwbs"

@app.route('/recommend_events_by_prompt', methods=['POST'])
def recommend_events_by_prompt():
    # Получение промта от пользователя
    data = request.get_json()
    user_prompt = data.get('prompt')
    if not user_prompt:
        return jsonify({'error': 'Prompt is required'}), 400

    # Извлечение всех событий из коллекции events_main
    events_ref = db.collection('events_main')
    all_events = [event.to_dict() for event in events_ref.stream()]

    if not all_events:
        return jsonify({'error': 'No events found'}), 404

    # Формирование данных для GPT-4
    prompt_data = {
        "user_prompt": user_prompt,
        "events": all_events
    }

    # Формирование тела запроса к Azure OpenAI
    azure_payload = {
        "messages": [
            {"role": "system", "content": "тебе предоставлен запрос человека и все ивенты из базы данных. Тебе надо скинуть только текст в формате [id1, id2, ...], где айди это айди ивентов которые подходят! НИЧЕГО ЛИШНЕГО"},
            {"role": "user", "content": f"Here is the data:\n{prompt_data}"}
        ],
        "max_tokens": 500,
        "temperature": 0.7
    }

    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_API_KEY
    }

    try:
        response = requests.post(AZURE_API_URL, headers=headers, json=azure_payload)
        response.raise_for_status()
        recommendations_text = response.json().get('choices', [{}])[0].get('message', {}).get('content', '')
        print(recommendations_text)

        # Преобразование строки в список
        try:
            recommendations_json = json.loads(recommendations_text)
        except json.JSONDecodeError:
            return jsonify({'error': 'Failed to parse recommendations as JSON'}), 500

    except requests.RequestException as e:
        return jsonify({'error': f"Failed to get recommendations: {str(e)}"}), 500

    # Достаём ивенты по айдишникам
    recommended_events = []
    for event_id in recommendations_json:
        event = next((e for e in all_events if e['id'] == event_id), None)
        if event:
            recommended_events.append(event)

    # Возврат ответа с рекомендованными ивентами
    return jsonify({'recommendations': recommended_events})

@app.route('/delete_users', methods=['POST'])
def delete_users():
    try:
        # Получаем ссылку на коллекцию 'users'
        users_ref = db.collection('users')

        # Получаем все документы из коллекции
        docs = users_ref.stream()

        # Удаляем каждый документ
        for doc in docs:
            doc.reference.delete()

        return 'Коллекция users была удалена.', 200
    except Exception as e:
        return str(e), 500
    

from datetime import datetime
from flask import request, flash

@app.route("/create_real_event", methods=["GET", "POST"])
def create_real_event():
    if request.method == "POST":
        # Получаем данные из формы
        event_name = request.form.get("name")
        description = request.form.get("description")
        location = request.form.get("location")
        price = request.form.get("price")
        date = request.form.get("date")
        category = request.form.get("category")

        # Пример ID пользователя, которого вы хотите обновить
        user_id = 'bOEYgRcegotVmGQx0pJR'

        # Получаем ссылку на пользователя
        user_ref = db.collection('users').document(user_id)

        # Получаем текущие данные пользователя
        user_data = user_ref.get().to_dict()

        # Создаем событие в events_main
        events_ref = db.collection('events_main')
        event_ref = events_ref.add({
            'url': 'https://cdn.britannica.com/38/196638-050-94E05EF4/Santa-Claus.jpg',
            'name': event_name,
            'location': location,
            'price': price,
            'description': description,
            'date': date,
            'time': '14:00',
            'category': category
        })

        # Получаем ID события
        event_id = event_ref[1].id  # event_ref returns a tuple; use the second element for the ID

        # Форматируем дату
        formatted_date = datetime.now().strftime('%d-%m-%Y')

        # Обновляем список "creations" пользователя
        if user_data:
            creations = user_data.get('creations', [])
            creations.append({
                'createdAt': formatted_date,  # Добавляем временную метку
                'event_id': event_id,  # Используем реальный event_id
            })

            user_ref.update({
                'creations': creations
            })

        flash("Event created successfully!")
    return "Form submitted"  # Adjust as needed (e.g., redirect to another page)

@app.route("/get_user_events", methods=["GET"])
def get_user_events():
    user_id = 'bOEYgRcegotVmGQx0pJR'
    try:
        # Получаем данные пользователя
        user_ref = db.collection('users').document(user_id)
        user_data = user_ref.get().to_dict()

        if not user_data:
            return jsonify({"error": "User not found"}), 404

        # Получаем список созданных событий
        creations = user_data.get('creations', [])
        event_ids = [creation.get('event_id') for creation in creations if 'event_id' in creation]

        # Получаем данные всех событий из коллекции events_main
        events_ref = db.collection('events_main')
        events = []

        for event_id in event_ids:
            event_doc = events_ref.document(event_id).get()
            if event_doc.exists:
                events.append({"id": event_id, **event_doc.to_dict()})

        return jsonify({"user_id": user_id, "events": events})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/delete_last_event", methods=["POST"])
def delete_last_event():
    # Пример ID пользователя, которого вы хотите обновить
    user_id = 'bOEYgRcegotVmGQx0pJR'

    # Получаем ссылку на пользователя
    user_ref = db.collection('users').document(user_id)

    # Получаем текущие данные пользователя
    user_data = user_ref.get().to_dict()

    if user_data:
        creations = user_data.get('creations', [])

        if creations:
            # Удаляем последний созданный ивент
            last_event = creations.pop()  # Удаляем последний элемент
            event_id = last_event.get('event_id')

            # Обновляем список creations в документе пользователя
            user_ref.update({
                'creations': creations
            })

            # Удаляем связанный ивент из коллекции events_main
            event_ref = db.collection('events_main').document(event_id)
            if event_ref.get().exists:
                event_ref.delete()

            flash("Last event deleted successfully!")
        else:
            flash("No events to delete.")
    else:
        flash("User not found.")

    return "Last event deleted"  # Настройте ответ (например, редирект на другую страницу)


if __name__ == '__main__':
    app.run(debug=True)
