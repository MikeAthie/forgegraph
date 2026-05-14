"""Run API streaming adapters split from adapters.api.runs.views."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403


def _build_stream_message(*, run: Run, event: RunEvent) -> dict[str, Any]:
    payload: dict[str, Any] = event.payload or {}
    message: dict[str, Any] = {
        "event_id": str(event.id),
        "timestamp": event.created_at.isoformat(),
        "type": event.event_type,
        "run_id": str(run.id),
        "trace_id": event.trace_id or run.trace_id,
        "category": normalize_event_category(
            event.event_type,
            category=str(payload.get("category") or ""),
            payload=payload,
        ),
    }
    if event.event_type == "run.updated":
        message["run"] = payload
    elif event.event_type == "node_run.updated":
        message["node_run"] = payload
    elif event.event_type == "node_stream.chunk":
        message["node_stream"] = payload
    else:
        message["payload"] = payload
    return add_event_level(message, payload=payload)


def _format_sse(message: dict[str, Any], event_name: str | None = None) -> str:
    payload = pyjson.dumps(message, default=str)
    lines = []
    if event_name:
        lines.append(f"event: {event_name}")
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"


def _get_user_from_request(request: Request) -> User | None:
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return cast(User, user)

    ticket_user = _user_from_stream_ticket(request)
    if ticket_user is not None:
        return ticket_user
    return _user_from_query_access_token(request)


def _user_from_stream_ticket(request: Request) -> User | None:
    ticket = str(request.query_params.get("ticket") or "").strip()
    if not ticket:
        return None
    ticket_payload = consume_ws_ticket(ticket)
    if not isinstance(ticket_payload, dict):
        return None
    permissions = ticket_payload.get("permissions")
    if isinstance(permissions, list) and "runs:view" not in permissions:
        return None
    access_jti = str(ticket_payload.get("access_jti") or "").strip()
    if access_jti and is_access_jti_revoked(access_jti):
        return None
    return _user_by_id(str(ticket_payload.get("user_id") or "").strip())


def _user_from_query_access_token(request: Request) -> User | None:
    if not getattr(settings, "RUN_STREAM_ALLOW_QUERY_ACCESS_TOKEN", False):
        return None

    token = request.query_params.get("token")
    if not token:
        return None

    access_token = validate_access_token(cast(Any, token))
    if access_token is None:
        return None

    user_id_claim = getattr(settings, "SIMPLE_JWT", {}).get("USER_ID_CLAIM", "user_id")
    user_id = access_token.get(user_id_claim)
    return _user_by_id(str(user_id or ""))


def _user_by_id(user_id: str) -> User | None:
    if not user_id:
        return None
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    try:
        return user_model.objects.get(id=user_id)
    except user_model.DoesNotExist:
        return None


async def _receive_with_timeout(channel_layer: Any, channel_name: str, timeout: float) -> Any:
    try:
        return await asyncio.wait_for(channel_layer.receive(channel_name), timeout=timeout)
    except TimeoutError:
        return None


class RunEventsStreamView(APIView):
    """Stream run events over Server-Sent Events (SSE)."""

    permission_classes = [AllowAny]

    def get(self, request: Request, run_id: UUID) -> StreamingHttpResponse | Response:
        user = _get_user_from_request(request)
        if not user or not getattr(user, "is_authenticated", False):
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            run = run_queryset_for_user(user).get(id=run_id)
        except Run.DoesNotExist:
            return Response({"detail": "Run not found"}, status=status.HTTP_404_NOT_FOUND)

        since_param = request.query_params.get("since")
        since = parse_datetime(since_param) if since_param else None
        requested_level = normalize_requested_event_level(request.query_params.get("event_level"))
        response = StreamingHttpResponse(
            self._event_stream(run=run, since=since, requested_level=requested_level),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        response["Connection"] = "keep-alive"
        return response

    def _event_stream(
        self,
        *,
        run: Run,
        since: datetime | None,
        requested_level: str,
    ) -> Any:
        yield _format_sse(
            {
                "type": "connected",
                "run_id": str(run.id),
                "timestamp": timezone.now().isoformat(),
                "level": requested_level,
            },
            event_name="connected",
        )
        yield from _historical_sse_events(run=run, since=since, requested_level=requested_level)
        yield from _live_sse_events(run=run, requested_level=requested_level)


def _historical_sse_events(
    *,
    run: Run,
    since: datetime | None,
    requested_level: str,
) -> Any:
    if since is None:
        return
    for event in RunEvent.objects.filter(run=run, created_at__gt=since).order_by("created_at"):
        message = _build_stream_message(run=run, event=event)
        if message_allowed_for_level(message, requested_level):
            yield _format_sse(message, event_name=event.event_type)


def _live_sse_events(*, run: Run, requested_level: str) -> Any:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    channel_name = async_to_sync(channel_layer.new_channel)()
    group_names = [
        run_event_group_name(run_id=str(run.id), level=level)
        for level in event_levels_for_subscription(requested_level)
    ]
    for group_name in group_names:
        async_to_sync(channel_layer.group_add)(group_name, channel_name)

    try:
        yield from _live_sse_messages(channel_layer, channel_name)
    except GeneratorExit:
        return
    finally:
        for group_name in group_names:
            async_to_sync(channel_layer.group_discard)(group_name, channel_name)


def _live_sse_messages(channel_layer: Any, channel_name: str) -> Any:
    while True:
        event = async_to_sync(_receive_with_timeout)(channel_layer, channel_name, 15)
        if event is None:
            yield ": ping\n\n"
            continue

        message = event.get("message")
        if message is None:
            continue

        event_type = message.get("type")
        yield _format_sse(message, event_name=str(event_type) if event_type else None)
