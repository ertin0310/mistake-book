"""设置页（方案三-17）：表单由 `config/user_fields.py` 的声明驱动。

**加一项资料 = 声明里加一条，这里一行不改。** 校验交给 `profile_service.clean()`，
本页只负责"按声明渲染 + 按声明落库"。

★ 每日复习时间点这一项特殊：改动不一定当日生效，规则在 `clock.decide_rollover_change`，
  默认 00:00 时**永远次日生效**（那条走不到的支路已在测试里钉住并要写进 README）。
"""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from config import prompts, user_fields, zone_list
from src.data.repository.profile_repo import ProfileRepo, SettingRepo
from src.domain import clock
from src.domain.errors import ValidationError
from src.services import profile_service
from src.web import csrf, decorators

bp = Blueprint("settings", __name__, url_prefix="/settings")

PENDING_KEYS = {"review_time": ("review_time_pending", "review_time_pending_from")}


@bp.get("/")
@decorators.require_login
def index():
    return _render({})


@bp.post("/")
@decorators.require_login
def save():
    try:
        csrf.validate(request.form.get(csrf.FORM_FIELD))
    except ValidationError as exc:
        abort_bad_request(exc.message)
    uid = decorators.current_user_id()
    profile, settings = ProfileRepo(g.conn, uid), SettingRepo(g.conn, uid)
    current = settings.all()
    values, errors = {}, []
    for field in user_fields.USER_FIELDS:
        if field.key == "mode":
            continue                                  # 模式由顶部开关管，不在设置页重复改
        try:
            values[field.key] = profile_service.clean(field, request.form.get(field.key, ""))
        except ValidationError as exc:
            errors.append(f"{field.label}：{exc.message}")

    if errors:
        return _render(request.form, errors)

    for field in user_fields.USER_FIELDS:
        if field.key not in values:
            continue
        if field.source == "setting":
            if field.key == "review_time":
                _save_review_time(settings, current, values[field.key])
            else:
                settings.set(field.key, values[field.key])
        else:
            _save_profile(profile, field.key, values[field.key])
    g.conn.commit()
    flash("设置已保存。", "success")
    return redirect(url_for("settings.index"))


def _save_review_time(settings, current, requested):
    change = profile_service.rollover_change(current.get("review_time", "00:00"), requested)
    if change.apply_immediately:
        settings.set("review_time", change.effective_value)
        settings.clear_pending(PENDING_KEYS["review_time"][0])
    else:
        settings.set(PENDING_KEYS["review_time"][0], change.pending_value)
        settings.set(PENDING_KEYS["review_time"][1], change.pending_from)
        flash(prompts.ROLLOVER_DEFERRED, "warning")


def _save_profile(profile, key, value):
    profile.conn.execute(f"UPDATE user_profile SET {key}=? WHERE user_id=?",
                         (value, profile.viewer_id))


def _render(form, errors=None):
    uid = decorators.current_user_id()
    stored = {**SettingRepo(g.conn, uid).all(), **ProfileRepo(g.conn, uid).profile()}
    fields = []
    for field in user_fields.USER_FIELDS:
        if field.key == "mode":
            continue
        fields.append({"field": field,
                       "value": form.get(field.key, stored.get(field.key, field.default)),
                       "zones": zone_list.options() if field.key == "time_zone" else ()})
    return render_template("settings/index.html", fields=fields,
                           errors=errors or [], username=decorators.current_username())


def abort_bad_request(message):
    from flask import abort
    abort(400, description=message)
