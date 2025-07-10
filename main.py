from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional
from dateutil.relativedelta import relativedelta
from decimal import Decimal, ROUND_HALF_UP
import calendar

app = FastAPI()

class RecurringItem(BaseModel):
    name: str
    amount: float
    start_date: str
    frequency: str # 'monthly', 'weekly', 'biweekly'

class ForecastRequest(BaseModel):
    starting_balance: float
    start_date: str
    end_date: str
    paychecks: List[RecurringItem]
    bills: List[RecurringItem]

@app.post("/forecast")
def generate_forecast(request: ForecastRequest):
    start_date = datetime.strptime(request.start_date, "%m-%d-%Y")
    end_date = datetime.strptime(request.end_date, "%m-%d-%Y")
    balance = request.starting_balance
    forecast = []

    current_date = start_date
    while current_date <= end_date:
        changes = []
        daily_change = 0
        # Add any paychecks on this date
        for income in request.paychecks:
            if matches_frequency(current_date, income):
                balance += income.amount
                daily_change += income.amount
                changes.append(
                    {
                        "name" : income.name,
                        "type" : "income",
                        "amount" : income.amount
                    }
                )

        # Subtract any bills on this date
        for bill in request.bills:
            if matches_frequency(current_date, bill):
                balance -= bill.amount
                daily_change -= bill.amount
                changes.append(
                    {
                        "name" : bill.name,
                        "type" : "bill",
                        "amount" : bill.amount
                    }
                )

        forecast.append(
            {
                "date" : current_date.strftime("%m-%d-%Y"),
                "balance" : round(balance, 2),
                "daily_change" : round(daily_change,2),
                "changes" : changes
            }
        )

        current_date += timedelta(days=1)
    
    return {
        "forecast" : forecast,
        "summary" : {
            "final_balance" : round(balance, 2),
            "lowest_balance" : min(f["balance"] for f in forecast),
            "first_negative_date" : next((f["date"] for f in forecast if f["balance"] < 0), None)
        }
    }

def matches_frequency(date: datetime, item: RecurringItem) -> bool:
    start = datetime.strptime(item.start_date, "%m-%d-%Y")
    delta_days = (date - start).days
    if delta_days < 0:
        return False
    elif item.frequency == "monthly":
        return date.day == start.day
    elif item.frequency == "weekly":
        return delta_days % 7 == 0
    elif item.frequency == "biweekly":
        return delta_days % 14 == 0
    return False


class Debt(BaseModel):
    name: str
    due_date: str
    current_balance: float
    apr: float
    minimum_payment: float

class PayoffRequest(BaseModel):
    start_date: str
    method: str # 'snowball', 'avalanche'
    extra_payment: float
    debt: List[Debt]

@app.post("/payoff")
def calculate_payoff(request: PayoffRequest):
    start_date = datetime.strptime(request.start_date, "%m-%d-%Y")
    extra_payment = request.extra_payment
    # total_debt = sum(d.current_balance for d in request.debt)
    payoff_schedule = []

    if request.method == "snowball":
        request.debt.sort(key=lambda d: d.current_balance)
    elif request.method == "avalanche":
        request.debt.sort(key=lambda d: d.apr, reverse=True)
    else:
        return #put something here later

    current_date = start_date
    current_month = True
    while request.debt:
        if current_date.month != start_date.month or (current_date.month == start_date.month and current_date.year != start_date.year):
            current_month = False
        for i, debt in enumerate(request.debt):
            if i == 0:
                "Apply extra payment to first bill since they should be ordered by pay off method"
                if is_due(current_date, debt) and current_month:
                    if debt.current_balance <= (debt.minimum_payment + extra_payment):
                        extra_payment += debt.minimum_payment
                        request.debt.pop(0)
                    else:
                        debt.current_balance -= Decimal(debt.minimum_payment + extra_payment)
                elif is_due(current_date, debt) and not current_month:
                    """Do something if minimum payment + extra payment is less than interest gained"""
                    interest_gained = round((debt.current_balance * (Decimal(debt.apr)/100)/12), 2)
                    debt.current_balance += interest_gained
                    if debt.current_balance <= (debt.minimum_payment + extra_payment):
                        extra_payment += debt.minimum_payment
                        request.debt.pop(0)
                    else:
                        debt.current_balance -= Decimal(debt.minimum_payment + extra_payment)
            else:
                if is_due(current_date, debt) and current_month:
                    if debt.current_balance <= debt.minimum_payment:
                        extra_payment += debt.minimum_payment
                        request.debt.pop(i)
                    else:
                        debt.current_balance -= Decimal(debt.minimum_payment)
                elif is_due(current_date, debt) and not current_month:
                    """Do something if minimum payment + extra payment is less than interest gained"""
                    interest_gained = round(debt.current_balance * (Decimal(debt.apr)/100)/12, 2)
                    debt.current_balance += interest_gained
                    if debt.current_balance <= debt.minimum_payment:
                        extra_payment += debt.minimum_payment
                        request.debt.pop(i)
                    else:
                        debt.current_balance -= Decimal(debt.minimum_payment)
            debt.current_balance = Decimal(debt.current_balance).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


        if is_last_day_of_month(current_date):
            debt = []
            for d in request.debt:
                debt.append(
                    {
                        "name": d.name,
                        "current_balance": d.current_balance
                    }
                )
            total_debt = sum(d.current_balance for d in request.debt)
            payoff_schedule.append(
                {
                    "date" : current_date.strftime("%m-%d-%Y"),
                    "total_debt" : round(total_debt, 2),
                    "extra_payment" : extra_payment,
                    "debt" : debt
                }
            )
        current_date += timedelta(days=1)
    
    time_passed = relativedelta(current_date, start_date)

    return {
        "schedule" : payoff_schedule,
        "time_to_payoff": {
            "years": time_passed.years,
            "months": time_passed.months,
            "days": time_passed.days
        }
    }

def is_due(date: datetime, debt: Debt) -> bool:
    due_date = datetime.strptime(debt.due_date, "%m-%d-%Y")
    if date.day == due_date.day:
        return True
    return False

def is_last_day_of_month(date: datetime) -> bool:
    last_day = calendar.monthrange(date.year, date.month)[1]
    return date.day == last_day