from flask import Flask, render_template, request, redirect, session, url_for, flash
import firebase_admin
from firebase_admin import credentials, firestore, storage
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from werkzeug.utils import secure_filename

# Инициализация Firebase
cred = credentials.Certificate('bs-hack1-firebase-adminsdk-glq41-85d5b66367.json')  # Замените на путь к вашему JSON-файлу
firebase_admin.initialize_app(cred, {
    'storageBucket': 'bs-hack1.appspot.com'  # Замените на имя вашего бакета
})
db = firestore.client()
bucket = storage.bucket()  # Получаем ссылку на хранилище

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Вы должны изменить это на случайный секретный ключ

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
    # Fetch posts and sort them by 'created_at' in descending order
    posts_ref = db.collection('posts').order_by('created_at', direction=firestore.Query.DESCENDING)
    posts = posts_ref.stream()
    
    # Prepare the list of posts with formatted 'created_at' and likes count
    posts_list = []
    for post in posts:
        post_data = post.to_dict()
        post_data['id'] = post.id  # Include post ID
        post_data['created_at_str'] = post_data['created_at'].strftime('%Y-%m-%d %H:%M:%S') if post_data.get('created_at') else 'N/A'
        post_data['likes_count'] = post_data.get('likes_count', 0)  # Get like count, default to 0
        posts_list.append(post_data)
    
    # Fetch liked posts for the current user
    liked_posts_ref = db.collection('likes').where('user_id', '==', session['user_id']).stream()
    liked_post_ids = [like.to_dict()['post_id'] for like in liked_posts_ref]

    return render_template('index.html', posts=posts_list, liked_posts=liked_post_ids)





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


@app.route('/like/<post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    user_id = session['user_id']
    
    # Check if the user has already liked this post
    like_ref = db.collection('likes').where('post_id', '==', post_id).where('user_id', '==', user_id).stream()
    if any(like_ref):
        flash('You have already liked this post', 'warning')
        return redirect(url_for('index'))

    # Add like to the 'likes' collection
    db.collection('likes').add({
        'post_id': post_id,
        'user_id': user_id
    })

    # Increment the like count for the post
    post_ref = db.collection('posts').document(post_id)
    post_ref.update({
        'likes_count': firestore.Increment(1)  # Increment like count by 1
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Search for user by username
        users_ref = db.collection('users').where('username', '==', username).stream()
        
        user = None
        user_id = None
        
        # Get the first document found
        for doc in users_ref:
            user = doc.to_dict()
            user_id = doc.id  # Get the document ID
            break
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user_id
            session['username'] = user['username']  # Store username in session
            return redirect('/index')
        else:
            flash('Invalid username or password')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        # Create a new document with a unique ID
        user_ref = db.collection('users').document()
        user_ref.set({
            'username': username,
            'password': hashed_password,
            'userId': user_ref.id
        })

        # Store userId and username in session
        session['user_id'] = user_ref.id
        session['username'] = username  # Store username in session

        return redirect('/index')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect('/login')

if __name__ == '__main__':
    app.run(debug=True)
