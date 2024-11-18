import streamlit as st
import psycopg2
import hashlib
from PIL import Image
import io

# Initialize all session state attributes
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'viewing_recipe' not in st.session_state:
    st.session_state.viewing_recipe = None
if 'selected_recipe' not in st.session_state:
    st.session_state.selected_recipe = None
if 'show_signup' not in st.session_state:
    st.session_state.show_signup = False
if 'create_recipe' not in st.session_state:
    st.session_state.create_recipe = False

def get_db_connection():
    try:
        return psycopg2.connect(
            dbname="kooky_app",
            user="postgres",
            password="qwerty",
            host="localhost",
            port="5432"
        )
    except psycopg2.Error as e:
        st.error(f"Database connection failed: {e}")
        return None

def create_user(username, password, bio, profile_picture, gender, dietary_preferences):
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        # Check if username already exists
        cursor.execute("SELECT 1 FROM users WHERE username = %s;", (username,))
        if cursor.fetchone():
            st.error("Username already exists!")
            return False
        
        # Hash the password
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        # Insert new user
        cursor.execute("""
            INSERT INTO users (username, password, bio, profile_picture, gender, dietary_preferences)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING user_id;
        """, (username, hashed_password, bio, profile_picture, gender, dietary_preferences))
        
        user_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        return user_id
    except psycopg2.Error as e:
        st.error(f"Error creating user: {e}")
        return False

# Modified make_recipe_public function (replaces delete_recipe)
def make_recipe_public(recipe_id, user_id):
    """Make a recipe public instead of deleting it."""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # Update the recipe to mark it as public
        cursor.execute("""
            UPDATE recipes 
            SET is_public = TRUE
            WHERE recipe_id = %s AND user_id = %s
            RETURNING recipe_id;
        """, (recipe_id, user_id))
        
        affected_rows = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        return affected_rows > 0
        
    except psycopg2.Error as e:
        st.error(f"Error making recipe public: {e}")
        return False

def create_new_recipe(title, description, ingredients, instructions, user_id):
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        # Get username of the current user to use as author
        cursor.execute("SELECT username FROM users WHERE user_id = %s;", (user_id,))
        author = cursor.fetchone()[0]
        
        cursor.execute("""
            INSERT INTO recipes (title, author, description, ingredients, instructions, user_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING recipe_id;
        """, (title, author, description, ingredients, instructions, user_id))
        
        recipe_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        return recipe_id
    except psycopg2.Error as e:
        st.error(f"Error creating recipe: {e}")
        return False

def get_user_profile(user_id):
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT username, bio, profile_picture, gender, dietary_preferences
            FROM users WHERE user_id = %s;
        """, (user_id,))
        profile = cursor.fetchone()
        cursor.close()
        conn.close()
        return profile
    except psycopg2.Error as e:
        st.error(f"Error fetching profile: {e}")
        return None

def update_user_profile(user_id, bio, profile_picture, gender, dietary_preferences):
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET bio = %s, profile_picture = %s, gender = %s, dietary_preferences = %s
            WHERE user_id = %s;
        """, (bio, profile_picture, gender, dietary_preferences, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except psycopg2.Error as e:
        st.error(f"Error updating profile: {e}")
        return False

def authenticate_user(username, password):
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, password FROM users WHERE username = %s;",
            (username,)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user and user[1] == hashlib.sha256(password.encode()).hexdigest():
            return user[0]
        return None
    except psycopg2.Error as e:
        st.error(f"Authentication error: {e}")
        return None

# Modified fetch_all_recipes function
def fetch_all_recipes():
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, author, description, ingredients, 
                   instructions, saved, recipe_id, user_id 
            FROM recipes
            WHERE is_public = TRUE;
        """)
        recipes = cursor.fetchall()
        cursor.close()
        conn.close()
        return recipes
    except psycopg2.Error as e:
        st.error(f"Error fetching recipes: {e}")
        return []

# Modified fetch_user_recipes function
def fetch_user_recipes(user_id):
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, author, description, ingredients, 
                   instructions, saved, recipe_id, user_id 
            FROM recipes 
            WHERE user_id = %s AND (is_public = FALSE OR is_public IS NULL);
        """, (user_id,))
        recipes = cursor.fetchall()
        cursor.close()
        conn.close()
        return recipes
    except psycopg2.Error as e:
        st.error(f"Error fetching user recipes: {e}")
        return []


def fetch_saved_recipes(user_id):
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.id, r.title, r.author, r.description, r.ingredients, 
                   r.instructions, r.saved, r.recipe_id, r.user_id 
            FROM recipes r
            JOIN saved_recipes sr ON r.recipe_id = sr.recipe_id
            WHERE sr.user_id = %s;
        """, (user_id,))
        recipes = cursor.fetchall()
        cursor.close()
        conn.close()
        return recipes
    except psycopg2.Error as e:
        st.error(f"Error fetching saved recipes: {e}")
        return []

def toggle_save_recipe(recipe_id, user_id, is_saved):
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        if is_saved:
            cursor.execute(
                "DELETE FROM saved_recipes WHERE recipe_id = %s AND user_id = %s;",
                (recipe_id, user_id)
            )
        else:
            cursor.execute(
                "INSERT INTO saved_recipes (recipe_id, user_id) VALUES (%s, %s);",
                (recipe_id, user_id)
            )
        conn.commit()
        cursor.close()
        conn.close()
    except psycopg2.Error as e:
        st.error(f"Error updating saved recipe: {e}")

def update_recipe(recipe_id, ingredients, instructions):
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE recipes SET ingredients = %s, instructions = %s WHERE recipe_id = %s;",
            (ingredients, instructions, recipe_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except psycopg2.Error as e:
        st.error(f"Error updating recipe: {e}")

def is_recipe_saved(recipe_id, user_id):
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM saved_recipes WHERE recipe_id = %s AND user_id = %s;",
            (recipe_id, user_id)
        )
        is_saved = cursor.fetchone() is not None
        cursor.close()
        conn.close()
        return is_saved
    except psycopg2.Error as e:
        st.error(f"Error checking saved status: {e}")
        return False

def unpack_recipe(recipe):
    try:
        if len(recipe) == 9:
            return {
                'id': recipe[0],
                'title': recipe[1],
                'author': recipe[2],
                'description': recipe[3],
                'ingredients': recipe[4],
                'instructions': recipe[5],
                'saved': recipe[6],
                'recipe_id': recipe[7],
                'user_id': recipe[8]
            }
        else:
            st.error(f"Invalid recipe format: expected 9 fields, got {len(recipe)}")
            return None
    except Exception as e:
        st.error(f"Error unpacking recipe: {e}")
        return None
def delete_recipe(recipe_id, user_id):
    """Delete a recipe from the database if it belongs to the user."""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # First verify that the recipe exists and belongs to the user
        cursor.execute("""
            SELECT 1 FROM recipes 
            WHERE recipe_id = %s AND user_id = %s;
        """, (recipe_id, user_id))
        
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return False
            
        # Delete the recipe if it exists and belongs to the user
        cursor.execute("""
            DELETE FROM recipes 
            WHERE recipe_id = %s AND user_id = %s;
        """, (recipe_id, user_id))
        
        # Delete any saved references to this recipe
        cursor.execute("""
            DELETE FROM saved_recipes 
            WHERE recipe_id = %s;
        """, (recipe_id,))
        
        affected_rows = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        return affected_rows > 0
        
    except psycopg2.Error as e:
        st.error(f"Error");

# Modified display_recipe_card function
def display_recipe_card(recipe_data, button_key_prefix):
    with st.container():
        st.markdown(f"""
            <div class="recipe-box">
                <h3 class="recipe-title">{recipe_data['title']}</h3>
                <p class="recipe-author">By {recipe_data['author']}</p>
                <p class="recipe-description">{recipe_data['description']}</p>
            </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button(f"View Recipe {recipe_data['recipe_id']}", 
                       key=f"{button_key_prefix}-view-{recipe_data['recipe_id']}"):
                st.session_state.viewing_recipe = recipe_data
        
        with col2:
            if button_key_prefix in ["explore", "saved"]:
                is_saved = is_recipe_saved(recipe_data['recipe_id'], st.session_state.user_id)
                if st.button(
                    f"{'Unsave' if is_saved else 'Save'} Recipe {recipe_data['recipe_id']}", 
                    key=f"{button_key_prefix}-save-{recipe_data['recipe_id']}"
                ):
                    toggle_save_recipe(recipe_data['recipe_id'], st.session_state.user_id, is_saved)
                    st.rerun()
            elif button_key_prefix == "my":
                if st.button(f"Edit Recipe {recipe_data['recipe_id']}", 
                           key=f"{button_key_prefix}-edit-{recipe_data['recipe_id']}"):
                    st.session_state.selected_recipe = recipe_data
        
        with col3:
            # Modified to show "Make Public" instead of "Delete"
            if button_key_prefix == "my":
                if st.button(f"Delete {recipe_data['recipe_id']}", 
                           key=f"{button_key_prefix}-public-{recipe_data['recipe_id']}",
                           type="primary"):
                    if make_recipe_public(recipe_data['recipe_id'], st.session_state.user_id):
                        st.success("Recipe moved to Explore page!")
                        st.rerun()
                    else:
                        st.error("Failed to make recipe public.")

# Streamlit UI
st.set_page_config(page_title="KOOKY", layout="centered")

# Login/Signup section
if not st.session_state.logged_in:
    st.title("Welcome to KOOKY")
    
    # Toggle between login and signup
    if st.button("Switch to " + ("Login" if st.session_state.show_signup else "Sign Up")):
        st.session_state.show_signup = not st.session_state.show_signup
    
    if st.session_state.show_signup:
        st.header("Create New Account")
        new_username = st.text_input("Username")
        new_password = st.text_input("Password", type="password")
        bio = st.text_area("Bio")
        profile_pic = st.file_uploader("Profile Picture", type=['png', 'jpg', 'jpeg'])
        gender = st.selectbox("Gender", ["", "Male", "Female", "Non-binary", "Prefer not to say"])
        dietary_prefs = st.multiselect("Dietary Preferences", 
            ["Vegetarian", "Vegan", "Gluten-free", "Dairy-free", "Keto", "Paleo"])
        
        if st.button("Sign Up"):
            if new_username and new_password:
                profile_pic_bytes = profile_pic.read() if profile_pic else None
                dietary_prefs_str = ", ".join(dietary_prefs) if dietary_prefs else None
                
                user_id = create_user(
                    new_username, 
                    new_password,
                    bio,
                    profile_pic_bytes,
                    gender,
                    dietary_prefs_str
                )
                
                if user_id:
                    st.session_state.logged_in = True
                    st.session_state.user_id = user_id
                    st.success("Account created successfully!")
                    st.rerun()
    else:
        st.header("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
if st.button("Login"):
    user_id = authenticate_user(username, password)
    if user_id:
        st.session_state.logged_in = True
        st.session_state.user_id = user_id
        st.success(f"Welcome back, {username}!")
        st.rerun()
    else:
        st.error("Invalid username or password")  # Ensure indentation is correct here


# Main app logic
if st.session_state.logged_in:
    st.sidebar.title("KOOKY")
    page = st.sidebar.radio("Navigate", ["Dashboard", "Explore", "Profile"])
    
    if page == "Profile":
        st.header("Your Profile")
        profile = get_user_profile(st.session_state.user_id)
        
        if profile:
            username, bio, profile_pic, gender, dietary_prefs = profile
            
            # Display current profile info
            st.subheader(f"Welcome, {username}!")
            
            # Display profile picture if exists
            if profile_pic:
                try:
                    image = Image.open(io.BytesIO(profile_pic))
                    st.image(image, width=200)
                except Exception as e:
                    st.error(f"Error loading profile picture: {e}")
            
            # Show current bio and preferences
            if bio:
                st.write("Bio:", bio)
            if gender:
                st.write("Gender:", gender)
            if dietary_prefs:
                st.write("Dietary Preferences:", dietary_prefs)
            
            # Update profile section
            st.subheader("Update Profile")
            new_bio = st.text_area("Bio", value=bio if bio else "")
            new_profile_pic = st.file_uploader("Update Profile Picture", type=['png', 'jpg', 'jpeg'])
            new_gender = st.selectbox("Gender", 
                ["", "Male", "Female", "Non-binary", "Prefer not to say"],
                index=["", "Male", "Female", "Non-binary", "Prefer not to say"].index(gender) if gender else 0
            )
            current_prefs = dietary_prefs.split(", ") if dietary_prefs else []
            new_dietary_prefs = st.multiselect("Dietary Preferences",
                ["Vegetarian", "Vegan", "Gluten-free", "Dairy-free", "Keto", "Paleo"],
                default=current_prefs
            )
            
            if st.button("Update Profile"):
                new_pic_bytes = new_profile_pic.read() if new_profile_pic else profile_pic
                new_prefs_str = ", ".join(new_dietary_prefs) if new_dietary_prefs else None
                
                if update_user_profile(
                    st.session_state.user_id,
                    new_bio,
                    new_pic_bytes,
                    new_gender,
                    new_prefs_str
                ):
                    st.success("Profile updated successfully!")
                    st.rerun()
    
    elif page == "Dashboard":
        # Add Create Recipe button at the top
        if st.button("Create New Recipe"):
            st.session_state.create_recipe = True
            st.session_state.viewing_recipe = None
            st.session_state.selected_recipe = None
        
        # Recipe Creator
        if st.session_state.create_recipe:
            st.header("Create New Recipe")
            new_recipe_title = st.text_input("Recipe Title")
            new_recipe_description = st.text_area("Recipe Description")
            new_recipe_ingredients = st.text_area("Ingredients")
            new_recipe_instructions = st.text_area("Instructions")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Save Recipe"):
                    if new_recipe_title and new_recipe_ingredients and new_recipe_instructions:
                        recipe_id = create_new_recipe(
                            new_recipe_title,
                            new_recipe_description,
                            new_recipe_ingredients,
                            new_recipe_instructions,
                            st.session_state.user_id
                        )
                        if recipe_id:
                            st.success("Recipe created successfully!")
                            st.session_state.create_recipe = False
                            st.rerun()
                    else:
                        st.error("Please fill in all required fields (Title, Ingredients, Instructions)")
            
            with col2:
                if st.button("Cancel"):
                    st.session_state.create_recipe = False
                    st.rerun()
        
        # Your Recipes Section
        st.header("Your Recipes")
        user_recipes = fetch_user_recipes(st.session_state.user_id)
        
        if user_recipes:
            for recipe in user_recipes:
                recipe_data = unpack_recipe(recipe)
                if recipe_data:
                    display_recipe_card(recipe_data, "my")
        else:
            st.write("You have no recipes yet.")
        
        # Saved Recipes Section
        st.header("Saved Recipes")
        saved_recipes = fetch_saved_recipes(st.session_state.user_id)
        
        if saved_recipes:
            for recipe in saved_recipes:
                recipe_data = unpack_recipe(recipe)
                if recipe_data:
                    display_recipe_card(recipe_data, "saved")
        else:
            st.write("You haven't saved any recipes yet.")
    
    elif page == "Explore":
        st.header("Explore Public Recipes")
        all_recipes = fetch_all_recipes()
        for recipe in all_recipes:
            recipe_data = unpack_recipe(recipe)
            if recipe_data:
                display_recipe_card(recipe_data, "explore")

# Recipe viewer
if st.session_state.viewing_recipe:
    st.sidebar.header(f"Viewing: {st.session_state.viewing_recipe['title']}")
    st.sidebar.subheader("Ingredients")
    st.sidebar.text(st.session_state.viewing_recipe['ingredients'])
    st.sidebar.subheader("Instructions")
    st.sidebar.text(st.session_state.viewing_recipe['instructions'])
    if st.sidebar.button("Close View"):
        st.session_state.viewing_recipe = None

# Recipe editor
if st.session_state.selected_recipe:
    recipe_data = st.session_state.selected_recipe
    st.sidebar.header(f"Editing: {recipe_data['title']}")
    new_ingredients = st.sidebar.text_area("Ingredients", recipe_data['ingredients'])
    new_instructions = st.sidebar.text_area("Instructions", recipe_data['instructions'])
    if st.sidebar.button("Save Changes"):
        update_recipe(recipe_data['recipe_id'], new_ingredients, new_instructions)
        st.session_state.selected_recipe = None
        st.rerun()
    if st.sidebar.button("Cancel"):
        st.session_state.selected_recipe = None
        st.rerun()