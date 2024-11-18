from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import hashlib
from functools import wraps
import jwt
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:qwerty@localhost/kooky_app'
app.config['SECRET_KEY'] = 'your-secret-key'
db = SQLAlchemy(app)
with app.app_context():
    db.session.execute("""
        CREATE OR REPLACE FUNCTION get_user_statistics(user_id_param INTEGER)
        RETURNS TABLE (
            total_recipes INTEGER,
            saved_recipes INTEGER,
            avg_saves_per_recipe FLOAT,
            most_popular_recipe VARCHAR
        ) AS $$
        BEGIN
            RETURN QUERY
            WITH user_stats AS (
                SELECT 
                    COUNT(DISTINCT r.recipe_id) as total_recipes,
                    COUNT(DISTINCT sr.recipe_id) as saved_recipes,
                    COALESCE(AVG(recipe_saves.save_count), 0) as avg_saves,
                    FIRST_VALUE(r.title) OVER (ORDER BY recipe_saves.save_count DESC) as popular_recipe
                FROM users u
                LEFT JOIN recipes r ON u.user_id = r.user_id
                LEFT JOIN saved_recipes sr ON u.user_id = sr.user_id
                LEFT JOIN (
                    SELECT recipe_id, COUNT(*) as save_count
                    FROM saved_recipes
                    GROUP BY recipe_id
                ) recipe_saves ON r.recipe_id = recipe_saves.recipe_id
                WHERE u.user_id = user_id_param
            )
            SELECT 
                total_recipes,
                saved_recipes,
                avg_saves,
                popular_recipe
            FROM user_stats;
        END;
        $$ LANGUAGE plpgsql;
    """)
    db.session.execute("""
        CREATE OR REPLACE FUNCTION update_recipe_saves()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                UPDATE recipes SET saved = true WHERE recipe_id = NEW.recipe_id;
            ELSIF TG_OP = 'DELETE' THEN
                UPDATE recipes SET saved = false 
                WHERE recipe_id = OLD.recipe_id 
                AND NOT EXISTS (
                    SELECT 1 FROM saved_recipes 
                    WHERE recipe_id = OLD.recipe_id
                );
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS update_recipe_saves_trigger ON saved_recipes;
        CREATE TRIGGER update_recipe_saves_trigger
        AFTER INSERT OR DELETE ON saved_recipes
        FOR EACH ROW
        EXECUTE FUNCTION update_recipe_saves();
    """)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user_id = data['user_id']
        except:
            return jsonify({'message': 'Invalid token'}), 401
        return f(current_user_id, *args, **kwargs)
    return decorated

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    result = db.session.execute("""
        SELECT user_id, username 
        FROM users 
        WHERE username = :username AND password = :password
    """, {'username': username, 'password': hashed_password})
    
    user = result.fetchone()
    
    if user:
        token = jwt.encode({
            'user_id': user[0],
            'username': user[1],
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, app.config['SECRET_KEY'])
        return jsonify({'token': token})
    
    return jsonify({'message': 'Invalid credentials'}), 401

@app.route('/api/recipes', methods=['GET'])
@token_required
def get_recipes(current_user_id):
    # Complex nested query with joins and aggregation
    result = db.session.execute("""
        WITH recipe_stats AS (
            SELECT 
                r.recipe_id,
                COUNT(sr.id) as save_count,
                COUNT(DISTINCT sr.user_id) as unique_savers
            FROM recipes r
            LEFT JOIN saved_recipes sr ON r.recipe_id = sr.recipe_id
            GROUP BY r.recipe_id
        )
        SELECT 
            r.recipe_id,
            r.title,
            r.author,
            r.description,
            r.ingredients,
            r.instructions,
            u.username as creator,
            rs.save_count,
            rs.unique_savers,
            EXISTS (
                SELECT 1 
                FROM saved_recipes sr 
                WHERE sr.recipe_id = r.recipe_id 
                AND sr.user_id = :user_id
            ) as is_saved
        FROM recipes r
        JOIN users u ON r.user_id = u.user_id
        JOIN recipe_stats rs ON r.recipe_id = rs.recipe_id
        ORDER BY rs.save_count DESC;
    """, {'user_id': current_user_id})
    
    recipes = result.fetchall()
    return jsonify([dict(row) for row in recipes])

@app.route('/api/user/statistics', methods=['GET'])
@token_required
def get_user_stats(current_user_id):
    # Using stored procedure
    result = db.session.execute(
        "SELECT * FROM get_user_statistics(:user_id)",
        {'user_id': current_user_id}
    )
    stats = result.fetchone()
    return jsonify(dict(stats))

@app.route('/api/recipes/<int:recipe_id>/save', methods=['POST'])
@token_required
def save_recipe(current_user_id, recipe_id):
    try:
        db.session.execute("""
            INSERT INTO saved_recipes (recipe_id, user_id)
            VALUES (:recipe_id, :user_id)
        """, {'recipe_id': recipe_id, 'user_id': current_user_id})
        db.session.commit()
        return jsonify({'message': 'Recipe saved successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 400

@app.route('/api/recipes/search', methods=['GET'])
@token_required
def search_recipes(current_user_id):
    query = request.args.get('q', '')
    dietary_pref = request.args.get('dietary_preference', '')
    result = db.session.execute("""
        SELECT DISTINCT r.*, 
            u.username as creator,
            u.dietary_preferences,
            COUNT(sr.id) OVER (PARTITION BY r.recipe_id) as save_count
        FROM recipes r
        JOIN users u ON r.user_id = u.user_id
        LEFT JOIN saved_recipes sr ON r.recipe_id = sr.recipe_id
        WHERE 
            (r.title ILIKE :query OR 
             r.description ILIKE :query OR 
             r.ingredients ILIKE :query) AND
            (:dietary_pref = '' OR u.dietary_preferences LIKE :dietary_pref_pattern)
        ORDER BY save_count DESC;
    """, {
        'query': f'%{query}%',
        'dietary_pref': dietary_pref,
        'dietary_pref_pattern': f'%{dietary_pref}%'
    })
    
    recipes = result.fetchall()
    return jsonify([dict(row) for row in recipes])

if __name__ == '__main__':
    app.run(debug=True)
