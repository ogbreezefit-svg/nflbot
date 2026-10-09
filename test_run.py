import nfl_data_py as nfl
import pandas as pd

print("Waking up the bot...")
print("Downloading current NFL team stats...")

# Pull basic team information from the NFL database
teams = nfl.import_team_desc()

# Tell it to just show us the first 5 teams it finds
print(teams[['team_abbr', 'team_name', 'team_conf']].head())
print("Data connection successful!")