
import json
import math


# ==========================================
# ACCOUNT CONFIGURATION
# ==========================================

TOTAL_CAPITAL = 100_000

MAX_DEPLOYMENT = 60_000

MAX_RISK_PER_TRADE = 500

MAX_AGGREGATE_OPEN_RISK = MAX_RISK_PER_TRADE * 3

MAX_OPEN_POSITIONS = 3

MAX_POSITION_VALUE = (
    MAX_DEPLOYMENT / MAX_OPEN_POSITIONS
)


# ==========================================
# NUMERIC VALIDATION
# ==========================================

def finite_number(value, field_name):

    if isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be a valid number"
        )

    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{field_name} must be a valid number"
        )

    if not math.isfinite(number):
        raise ValueError(
            f"{field_name} must be finite"
        )

    return number


# ==========================================
# VALIDATE ACCOUNT STATE
# ==========================================

def validate_account(account):

    if not isinstance(account, dict):
        raise ValueError("Account must be a dictionary")

    required = [
        "total_capital",
        "deployed_capital",
        "open_positions_count",
        "aggregate_open_risk",
    ]

    for key in required:
        if key not in account:
            raise ValueError(
                f"Missing account field: {key}"
            )

    total_capital = finite_number(
        account["total_capital"],
        "Total capital"
    )

    deployed_capital = finite_number(
        account["deployed_capital"],
        "Deployed capital"
    )

    open_positions = account["open_positions_count"]

    if isinstance(open_positions, bool):
        raise ValueError(
            "Open positions count must be an integer"
        )

    if not isinstance(open_positions, int):
        raise ValueError(
            "Open positions count must be an integer"
        )

    if total_capital <= 0:
        raise ValueError("Invalid total capital")

    if deployed_capital < 0:
        raise ValueError("Invalid deployed capital")

    if open_positions < 0:
        raise ValueError("Invalid open positions count")

    if open_positions > MAX_OPEN_POSITIONS:
        raise ValueError(
            "Open positions exceed maximum allowed"
        )

    effective_deployment_limit = min(
        MAX_DEPLOYMENT,
        total_capital
    )

    if deployed_capital > total_capital:
        raise ValueError(
            "Deployed capital exceeds total capital"
        )

    if deployed_capital > effective_deployment_limit:
        raise ValueError(
            "Deployed capital exceeds deployment limit"
        )

    aggregate_open_risk = finite_number(account["aggregate_open_risk"], "Aggregate open risk")
    if aggregate_open_risk < 0 or aggregate_open_risk > MAX_AGGREGATE_OPEN_RISK:
        raise ValueError("Aggregate open risk exceeds configured limit")

    return {
        "total_capital": total_capital,
        "deployed_capital": deployed_capital,
        "open_positions_count": open_positions,
        "aggregate_open_risk": aggregate_open_risk,
        "aggregate_risk_limit": MAX_AGGREGATE_OPEN_RISK,
        "deployment_limit": effective_deployment_limit
    }


# ==========================================
# REJECTION RESPONSE
# ==========================================

def reject(status, reason):

    return {
        "approved_for_sizing": False,
        "status": status,
        "reason": reason,
        "quantity": None,
        "manual_approval_required": True,
        "order_placed": False
    }


# ==========================================
# POSITION SIZE CALCULATION
# ==========================================

def calculate_position_size(candidate, account):

    # --------------------------------------
    # 1. VALIDATE ACCOUNT
    # --------------------------------------

    validated_account = validate_account(account)

    if not isinstance(candidate, dict):
        raise ValueError(
            "Candidate must be a dictionary"
        )

    # --------------------------------------
    # 2. CHECK CANDIDATE QUALIFICATION
    # --------------------------------------

    candidate_status = candidate.get(
        "candidate_status"
    )

    if candidate_status != "BREAKOUT_CONFIRMED":

        return reject(
            "REJECTED",
            "Candidate has not passed technical breakout qualification"
        )

    # --------------------------------------
    # 3. CHECK ENTRY AND STOP LOSS
    # --------------------------------------

    entry_price = candidate.get("entry_price")
    stop_loss = candidate.get("stop_loss")

    if entry_price is None or stop_loss is None:

        return reject(
            "MISSING_ENTRY_OR_STOP",
            "A valid entry price and structural stop-loss are required"
        )

    try:

        entry_price = finite_number(
            entry_price,
            "Entry price"
        )

        stop_loss = finite_number(
            stop_loss,
            "Stop-loss"
        )

    except ValueError as error:

        return reject(
            "INVALID_PRICES",
            str(error)
        )

    if entry_price <= 0 or stop_loss <= 0:

        return reject(
            "INVALID_PRICES",
            "Entry and stop-loss must be positive"
        )

    if stop_loss >= entry_price:

        return reject(
            "INVALID_STOP",
            "Stop-loss must be below entry price for this long cash-equity strategy"
        )

    # --------------------------------------
    # 4. CHECK OPEN POSITION LIMIT
    # --------------------------------------

    open_positions = validated_account[
        "open_positions_count"
    ]

    if open_positions >= MAX_OPEN_POSITIONS:

        return reject(
            "MAX_POSITIONS_REACHED",
            "Maximum open positions reached"
        )

    # --------------------------------------
    # 5. CHECK DEPLOYMENT CAPACITY
    # --------------------------------------

    deployed_capital = validated_account[
        "deployed_capital"
    ]

    deployment_limit = validated_account[
        "deployment_limit"
    ]

    available_deployment = (
        deployment_limit - deployed_capital
    )

    if available_deployment <= 0:

        return reject(
            "DEPLOYMENT_LIMIT_REACHED",
            "No deployment capacity available"
        )

    # --------------------------------------
    # 6. CALCULATE RISK PER SHARE
    # --------------------------------------

    risk_per_share = (
        entry_price - stop_loss
    )

    if risk_per_share <= 0:

        return reject(
            "INVALID_RISK",
            "Risk per share must be positive"
        )

    # --------------------------------------
    # 7. CALCULATE QUANTITY LIMITS
    # --------------------------------------

    remaining_risk = max(0, validated_account["aggregate_risk_limit"] - validated_account["aggregate_open_risk"])
    per_trade_budget = min(MAX_RISK_PER_TRADE, remaining_risk)
    if per_trade_budget <= 0:
        return reject("AGGREGATE_RISK_LIMIT_REACHED", "No aggregate portfolio risk capacity remains")
    quantity_by_risk = math.floor(per_trade_budget / risk_per_share)

    allocation_limit = min(
        MAX_POSITION_VALUE,
        available_deployment
    )

    quantity_by_allocation = math.floor(
        allocation_limit / entry_price
    )

    quantity = min(
        quantity_by_risk,
        quantity_by_allocation
    )

    if quantity <= 0:

        return reject(
            "INSUFFICIENT_CAPITAL",
            "Available allocation cannot purchase even one share within the risk limit"
        )

    # --------------------------------------
    # 8. FINAL POSITION CALCULATIONS
    # --------------------------------------

    investment_value = (
        quantity * entry_price
    )

    maximum_trade_risk = (
        quantity * risk_per_share
    )

    remaining_deployment = (
        deployment_limit
        - deployed_capital
        - investment_value
    )

    # Final defensive checks

    if maximum_trade_risk > MAX_RISK_PER_TRADE:

        raise ArithmeticError(
            "Calculated trade risk exceeds configured risk limit"
        )

    if investment_value > allocation_limit:

        raise ArithmeticError(
            "Calculated investment exceeds allocation limit"
        )

    # --------------------------------------
    # 9. RETURN POSITION SIZING
    # --------------------------------------

    return {

        "approved_for_sizing": True,

        "status": "SIZING_CALCULATED",

        "symbol": candidate.get("symbol"),

        "entry_price": round(entry_price, 2),

        "stop_loss": round(stop_loss, 2),

        "risk_per_share": round(
            risk_per_share, 2
        ),

        "quantity": int(quantity),

        "investment_value": round(
            investment_value, 2
        ),

        "maximum_trade_risk": round(
            maximum_trade_risk, 2
        ),

        "risk_budget": per_trade_budget,

        "allocation_limit": round(
            allocation_limit, 2
        ),

        "remaining_deployment": round(
            remaining_deployment, 2
        ),

        "manual_approval_required": True,

        "order_placed": False,

        "notes": [

            "Whole-share cash-equity position sizing",

            "No leverage or averaging down",

            "Charges and slippage are not included",

            "Actual execution price may differ from planned entry",

            "Stop-loss execution is not guaranteed",

            "Position sizing is not a trade recommendation",

            "Manual approval is required before any trade"
        ]
    }


# ==========================================
# MAIN TEST
# ==========================================

if __name__ == "__main__":

    candidate = {

        "symbol": "RELIANCE",

        "candidate_status": "NOT_QUALIFIED",

        "entry_price": None,

        "stop_loss": None
    }

    account = {

        "total_capital": TOTAL_CAPITAL,

        "deployed_capital": 0,

        "open_positions_count": 0,
        "aggregate_open_risk": 0,
    }

    result = calculate_position_size(
        candidate,
        account
    )

    print("\n========== RISK MANAGER ==========\n")

    print(
        json.dumps(
            result,
            indent=4
        )
    )
