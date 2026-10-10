from dotenv import load_dotenv
load_dotenv()  # Loads variables from .env into os.environ
from apscheduler.schedulers.blocking import BlockingScheduler
from clv_tracker import log_closing_lines
from settlement import grade_completed_picks
# Import your main pick-generation logic function here

scheduler = BlockingScheduler()

# 1. Run Pick Generator every 6 hours to scan new odds
# scheduler.add_job(run_strategy_pipeline, 'interval', hours=6)

# 2. Check & log Closing Lines every 15 minutes
scheduler.add_job(log_closing_lines, 'interval', minutes=15)

# 3. Grade completed picks every 2 hours
scheduler.add_job(grade_completed_picks, 'interval', hours=2)

if __name__ == "__main__":
    print("🚀 Shadow Mode Bot Scheduler Running...")
    scheduler.start()