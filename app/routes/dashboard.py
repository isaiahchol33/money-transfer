import io
from datetime import datetime, timedelta

import pandas as pd

from flask import Blueprint, render_template, request, send_file
from flask_login import login_required, current_user
from sqlalchemy import func, extract

from app import db
from app.models import Transaction

dashboard = Blueprint('dashboard', __name__)


# ================= HELPERS =================
def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d") if date_str else None
    except:
        return None


def get_filters():
    return {
        "start_date": parse_date(request.args.get("start_date")),
        "end_date": parse_date(request.args.get("end_date")),
        "search": request.args.get("search", "").strip(),
        "cashier": request.args.get("cashier")
    }


def apply_filters(query):
    f = get_filters()

    start_date = f["start_date"]
    end_date = f["end_date"]
    search = f["search"]
    cashier = f["cashier"]

    if end_date:
        end_date += timedelta(days=1)

    if current_user.role != "admin":
        query = query.filter(
            (Transaction.sender_cashier_id == current_user.id) |
            (Transaction.receiver_cashier_id == current_user.id)
        )

    if start_date:
        query = query.filter(Transaction.date >= start_date)

    if end_date:
        query = query.filter(Transaction.date < end_date)

    if search:
        query = query.filter(
            (Transaction.sender_name.ilike(f"%{search}%")) |
            (Transaction.receiver_name.ilike(f"%{search}%")) |
            (Transaction.sender_cashier_name.ilike(f"%{search}%")) |
            (Transaction.receiver_cashier_name.ilike(f"%{search}%")) |
            (Transaction.sender_location.ilike(f"%{search}%")) |
            (Transaction.receiver_location.ilike(f"%{search}%"))
        )

    if cashier:
        query = query.filter(Transaction.sender_cashier_name == cashier)

    return query


# ================= DASHBOARD =================
@dashboard.route('/dashboard')
@login_required
def dashboard_home():

    wallet = current_user.get_wallet()
    base_query = apply_filters(Transaction.query)

    page = request.args.get('page', 1, type=int)

    pagination = base_query.order_by(
        Transaction.date.desc()
    ).paginate(page=page, per_page=10, error_out=False)

    transactions = pagination.items

    # ================= KPI =================
    total_transactions = base_query.count()

    total_amount = base_query.with_entities(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).scalar() or 0

    total_commission = base_query.with_entities(
        func.coalesce(func.sum(Transaction.commission), 0)
    ).scalar() or 0

    # ================= MONTHLY COMPARISON =================
    now = datetime.utcnow()

    this_month_start = datetime(now.year, now.month, 1)

    last_month_start = (
        datetime(now.year - 1, 12, 1)
        if now.month == 1
        else datetime(now.year, now.month - 1, 1)
    )

    this_month_total = db.session.query(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).filter(
        Transaction.date >= this_month_start,
        Transaction.date <= now
    ).scalar() or 0

    last_month_total = db.session.query(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).filter(
        Transaction.date >= last_month_start,
        Transaction.date < this_month_start
    ).scalar() or 0

    growth_percent = (
        ((this_month_total - last_month_total) / last_month_total) * 100
        if last_month_total > 0 else (100 if this_month_total > 0 else 0)
    )

    # ================= CHART DATA =================

    # ✅ CROSS-DB MONTHLY
    monthly_raw = base_query.with_entities(
        extract('year', Transaction.date),
        extract('month', Transaction.date),
        func.sum(Transaction.amount)
    ).group_by(
        extract('year', Transaction.date),
        extract('month', Transaction.date)
    ).all()

    months = [
        f"{int(y)}-{int(m):02d}" for y, m, _ in monthly_raw
    ]
    monthly_amounts = [
        float(total or 0) for _, _, total in monthly_raw
    ]

    # ✅ CROSS-DB DAILY
    daily_raw = base_query.with_entities(
        extract('year', Transaction.date),
        extract('month', Transaction.date),
        extract('day', Transaction.date),
        func.count(Transaction.id)
    ).group_by(
        extract('year', Transaction.date),
        extract('month', Transaction.date),
        extract('day', Transaction.date)
    ).all()

    dates = [
        f"{int(y)}-{int(m):02d}-{int(d):02d}"
        for y, m, d, _ in daily_raw
    ]
    counts = [c for _, _, _, c in daily_raw]

    # USERS
    users_data = base_query.with_entities(
        Transaction.sender_cashier_name,
        func.count(Transaction.id)
    ).group_by(Transaction.sender_cashier_name).all()

    active_names = [u[0] or "Unknown" for u in users_data]
    active_counts = [u[1] for u in users_data]

    # LOCATIONS
    location_data = base_query.with_entities(
        Transaction.receiver_location,
        func.count(Transaction.id)
    ).group_by(Transaction.receiver_location).all()

    locations = [l[0] or "Unknown" for l in location_data]
    location_counts = [l[1] for l in location_data]

    # COMMISSION
    commission_data = base_query.with_entities(
        Transaction.receiver_location,
        func.sum(Transaction.commission)
    ).group_by(Transaction.receiver_location).all()

    commission_locations = [c[0] or "Unknown" for c in commission_data]
    commission_values = [float(c[1] or 0) for c in commission_data]

    # CASHIERS
    cashiers = db.session.query(
        Transaction.sender_cashier_name
    ).filter(
        Transaction.sender_cashier_name.isnot(None)
    ).distinct().all()

    cashiers = [c[0] for c in cashiers if c[0]]

    return render_template(
        "dashboard.html",

        wallet=wallet,
        transactions=transactions,
        pagination=pagination,

        **get_filters(),

        total_transactions=total_transactions,
        total_amount=round(total_amount, 2),
        total_commission=round(total_commission, 2),

        this_month_total=round(this_month_total, 2),
        last_month_total=round(last_month_total, 2),
        growth_percent=round(growth_percent, 2),

        currency="SSP",

        months=months,
        monthly_amounts=monthly_amounts,
        dates=dates,
        counts=counts,
        active_names=active_names,
        active_counts=active_counts,
        locations=locations,
        location_counts=location_counts,
        commission_locations=commission_locations,
        commission_values=commission_values,

        cashiers=cashiers,
        title="Dashboard"
    )


# ================= EXPORT =================
@dashboard.route('/export-excel')
@login_required
def export_excel():

    query = apply_filters(Transaction.query)
    transactions = query.order_by(Transaction.date.desc()).all()

    df = pd.DataFrame([{
        "Sender": t.sender_name or "",
        "Receiver": t.receiver_name or "",
        "Amount": float(t.amount or 0),
        "Fee": float(t.commission or 0),
        "Date": t.date.strftime("%Y-%m-%d %H:%M") if t.date else ""
    } for t in transactions])

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)

    output.seek(0)

    return send_file(
        output,
        download_name="transactions.xlsx",
        as_attachment=True
    )