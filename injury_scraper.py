def evaluate_team_health(team_name):
    """
    Evaluates team health and key starter status. 
    Returns status: 'HEALTHY', 'HEAVILY_INJURED', or 'CRITICAL_QB_OUT'.
    """
    # Active injury tracking dictionary for key roster players
    critical_injuries = {
        # Example: "Team Name": "CRITICAL_QB_OUT"
    }
    return critical_injuries.get(team_name, "HEALTHY")