"""Tornado WebSocket server that receives vehicle positions and broadcasts to UI clients."""

from __future__ import annotations

import json
import time
from typing import ClassVar

import msgspec
import tornado.ioloop
import tornado.web
import tornado.websocket

from .writers.base import PositionRecord


class VehicleState:
    """In-memory store of latest position per vehicle"""

    def __init__(self) -> None:
        self.vehicles: dict[str, dict] = {}

    def update(self, record: dict) -> None:
        vid = record["vehicle_id"]
        self.vehicles[vid] = record

    def snapshot(self) -> list[dict]:
        return list(self.vehicles.values())


state = VehicleState()


class DashboardSocket(tornado.websocket.WebSocketHandler):
    """WebSocket endpoint for the UI dashboard."""

    clients: ClassVar[set[DashboardSocket]] = set()

    def check_origin(self, origin: str) -> bool:
        return True  # Allow all origins for dev

    def open(self) -> None:
        DashboardSocket.clients.add(self)
        # Send current snapshot immediately on connect
        self.write_message(json.dumps({
            "type": "snapshot",
            "vehicles": state.snapshot(),
        }))
        print(f"[ws] Dashboard client connected ({len(DashboardSocket.clients)} total)")

    def on_close(self) -> None:
        DashboardSocket.clients.discard(self)
        print(f"[ws] Dashboard client disconnected ({len(DashboardSocket.clients)} total)")

    @classmethod
    def broadcast(cls, message: str) -> None:
        for client in cls.clients:
            try:
                client.write_message(message)
            except tornado.websocket.WebSocketClosedError:
                pass


class PositionHandler(tornado.web.RequestHandler):
    """HTTP endpoint that receives position batches from the simulator."""

    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self) -> None:
        self.set_status(204)

    def post(self) -> None:
        try:
            records = msgspec.json.decode(self.request.body, type=list[dict])
        except Exception:
            # Try single record
            try:
                record = msgspec.json.decode(self.request.body, type=dict)
                records = [record]
            except Exception as e:
                self.set_status(400)
                self.write({"error": str(e)})
                return

        updates = []
        for record in records:
            state.update(record)
            updates.append(record)

        # Broadcast to all connected dashboard clients
        if updates:
            msg = json.dumps({
                "type": "update",
                "vehicles": updates,
            })
            DashboardSocket.broadcast(msg)

        self.set_status(200)
        self.write({"accepted": len(updates)})


class HealthHandler(tornado.web.RequestHandler):
    def get(self) -> None:
        self.write({
            "status": "ok",
            "vehicles_tracked": len(state.vehicles),
            "dashboard_clients": len(DashboardSocket.clients),
        })


def make_app() -> tornado.web.Application:
    return tornado.web.Application([
        (r"/api/position", PositionHandler),
        (r"/ws/dashboard", DashboardSocket),
        (r"/health", HealthHandler),
    ])


def run_server(port: int = 8888) -> None:
    app = make_app()
    app.listen(port)
    print(f"[server] Listening on http://localhost:{port}")
    print(f"[server]   POST positions -> http://localhost:{port}/api/position")
    print(f"[server]   WS dashboard   -> ws://localhost:{port}/ws/dashboard")
    print(f"[server]   Health check   -> http://localhost:{port}/health")
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    run_server()
