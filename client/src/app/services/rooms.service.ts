import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

export interface RoomParticipant {
  name: string;
  role: string;
  initial: string;
  color: string;
  online: boolean;
}

export interface RoomState {
  code: string;
  hostName: string;
  participants: RoomParticipant[];
  createdAt: string;
  publicMessages: RoomChatMessage[];
  insights: RoomInsights;
}

export interface RoomChatMessage {
  sender: string;
  role: string;
  time: string;
  text: string;
  isAI?: boolean;
}

export interface InsightPoint {
  text: string;
}

export interface RoomInsights {
  reply: string;
  agreements: InsightPoint[];
  disagreements: InsightPoint[];
  compromises: InsightPoint[];
}

export interface CreateRoomRequest {
  name: string;
  code?: string;
}

export interface JoinRoomRequest {
  code: string;
  name: string;
}

export interface ChatMessage {
  role: 'user' | 'model';
  content: string;
}

export interface ChatResponse {
  reply: string;
  sources: string[];
}

@Injectable({ providedIn: 'root' })
export class RoomsService {
  private readonly apiUrl = 'http://localhost:8000/rooms';

  constructor(private http: HttpClient) {}

  createRoom(request: CreateRoomRequest): Promise<RoomState> {
    return firstValueFrom(
      this.http.post<RoomState>(this.apiUrl, request)
    );
  }

  joinRoom(request: JoinRoomRequest): Promise<RoomState> {
    return firstValueFrom(
      this.http.post<RoomState>(
        `${this.apiUrl}/${request.code}/join`,
        { name: request.name }
      )
    );
  }

  getRoom(code: string): Promise<RoomState> {
    return firstValueFrom(
      this.http.get<RoomState>(`${this.apiUrl}/${code}`)
    );
  }

  sendPrivateMessage(
    message: string,
    history: ChatMessage[],
    roomCode: string,
    senderName: string,
  ): Promise<ChatResponse> {
    return firstValueFrom(
      this.http.post<ChatResponse>(`${this.apiUrl.replace('/rooms', '')}/chat`, {
        message,
        history,
        roomCode,
        senderName,
      })
    );
  }

  sendPublicMessage(
    socket: WebSocket,
    sender: string,
    text: string,
  ): void {
    socket.send(JSON.stringify({
      action: 'send_public_message',
      sender,
      text,
    }));
  }

  connectToRoomUpdates(
    code: string,
    onRoomState: (room: RoomState) => void,
    onError?: (message: string) => void,
  ): WebSocket {
    const socket = new WebSocket(`ws://localhost:8000/rooms/${code}/ws`);

    socket.onmessage = (event) => {
      const response = JSON.parse(event.data);

      if (response.type === 'room_state' && response.room) {
        onRoomState(response.room as RoomState);
      }

      if (response.type === 'room_error') {
        onError?.(response.message ?? 'Room websocket error.');
      }
    };

    return socket;
  }
}