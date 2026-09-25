import time
import json
from pprint import pprint

from workdey import create_app
from workdey.db import db
from workdey.models import User, Profile, Watch, Match, Opportunity
from workdey.pipeline import run_user_now
from workdey.services import llm as llmsvc

def run_extensive_test():
    app = create_app()
    with app.app_context():
        print("=== 1. Setting up test user ===")
        # Check if demo user exists
        user = User.query.filter_by(email="esabublessing7@gmail.com").first()
        if not user:
            user = User(email="esabublessing7@gmail.com", password_hash="testpass", name="Blessing Esabu")
            db.session.add(user)
            db.session.commit()
            print(f"Created user {user.email}")
        
        # Setup Profile
        if not user.profile:
            profile = Profile(
                user_id=user.id,
                target_roles=["Backend Developer", "Software Engineer"],
                locations=["Remote", "Nigeria"],
                cv_text="I am a Backend Engineer with 4 years of experience in Python, Flask, Postgres, and APIs.",
                skills_tags=["Python", "Flask", "PostgreSQL", "API Design"],
                years_experience=4,
            )
            db.session.add(profile)
            profile.completeness_score()
            db.session.commit()
            print("Created profile for test user.")
        
        # Setup Watch
        if not user.watch:
            watch = Watch(
                user_id=user.id,
                enabled=True,
                cadence_hours=1,
                email_on=True,
                match_threshold=0.3
            )
            db.session.add(watch)
            db.session.commit()
            print("Created watch for test user.")

        print("\n=== 2. Zapping Email directly ===")
        from workdey.services.mailer import send_welcome
        row = send_welcome(user)
        db.session.commit()
        print(f"Sent Welcome Email: Status = {row.status}")

        print("\n=== 3. Triggering Apify Agent & Matching Workflow ===")
        print("This will call the Apify API, wait for the dataset, save matches, and trigger Brevo...")
        
        # The Apify run will take a moment depending on Apify's queue and scraper speed
        result = run_user_now(user)
        print("Apify run complete. Result:", result)
        
        print("\n=== 3. Testing Groq LLM Generation ===")
        # Let's test the LLM on the first match
        match = Match.query.filter_by(user_id=user.id).order_by(Match.created_at.desc()).first()
        if match:
            print(f"Found Match: {match.opportunity.title_guess} at {match.opportunity.author_name}")
            print("Generating customized CV tweak via Groq...")
            
            try:
                cv_draft = llmsvc.generate(user.profile, match, kind="cv", note="Please emphasize my Python skills.")
                print("\n--- Groq Output (CV) ---")
                print(cv_draft.get("body", "No body returned"))
                print("------------------------\n")
                
                print("Generating Cover Letter via Groq...")
                cover_draft = llmsvc.generate(user.profile, match, kind="cover", note="")
                print("\n--- Groq Output (Cover Letter) ---")
                print(cover_draft.get("body", "No body returned"))
                print("----------------------------------\n")
                print("Extensive test completely successful!")
            except Exception as e:
                print("Error during Groq LLM generation:", str(e))
        else:
            print("No matches were found in the database. Ensure Apify has found matches at least once.")
            
if __name__ == "__main__":
    run_extensive_test()
