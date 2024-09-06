from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy




app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///newFlask.db'
db = SQLAlchemy(app)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    title = db.Column(db.String(300), nullable = False)
    text = db.Column(db.Text, nullable = False)



@app.route("/")
@app.route("/index")
def index():
    return render_template('index.html')


@app.route("/about")
def about():
    return render_template('about.html')


@app.route('/create', methods = ['GET', 'POST'])
def create():
    if request.method == 'POST':
        title = request.form['title']
        text = request.form['text']

        post = Post(title = title, text = text)

        try:
            db.session.add(post)
            db.session.commit()
            return redirect('/index')
        except:
            return 'При добавлениие статьи произошла ошибка, повторите попытку'

        
    else:
        return render_template('create.html')

if __name__ == '__main__':
    app.run(debug=True)