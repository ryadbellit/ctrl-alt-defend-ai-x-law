import {
  Component,
  OnInit,
  ViewChild,
  ElementRef,
  AfterViewChecked,
  ChangeDetectorRef,
  OnDestroy,
} from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RoomsService, RoomParticipant } from '../../services/rooms.service';

export interface Message {
  id: number;
  sender: string;
  role: string;
  time: string;
  text: string;
  isAI?: boolean;
}

export interface InsightPoint {
  text: string;
}

@Component({
  selector: 'app-room',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './room.component.html',
  styleUrls: ['./room.component.scss'],
})
export class RoomComponent implements OnInit, AfterViewChecked, OnDestroy {
  @ViewChild('messagesContainer') messagesContainer!: ElementRef;

  roomCode = 'UNKNOWN';
  currentUserName = '';

  sessionActive = false;
  activeTab: 'public' | 'private' | 'agreement' = 'public';
  newMessage = '';
  codeCopied = false;
  isLoading = true;

  participants: RoomParticipant[] = [];

  messages: Message[] = [];

  agreements: InsightPoint[] = [];
  disagreements: InsightPoint[] = [];
  compromises: InsightPoint[] = [];

  private roomSocket?: WebSocket;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private roomsService: RoomsService,
    private cdr: ChangeDetectorRef,
  ) {}

  async ngOnInit(): Promise<void> {
    this.roomCode =
      this.route.snapshot.queryParamMap.get('code')?.toUpperCase() ?? 'UNKNOWN';

    this.currentUserName =
      this.route.snapshot.queryParamMap.get('name')?.trim() ?? '';

    if (this.roomCode === 'UNKNOWN') {
      this.router.navigate(['/']);
      return;
    }

    await this.loadRoom();
  }

  ngOnDestroy(): void {
    this.roomSocket?.close();
  }

  async loadRoom(): Promise<void> {
    this.isLoading = true;

    try {
      const room = await this.roomsService.getRoom(this.roomCode);

      this.roomCode = room.code;
      this.participants = room.participants;
      this.sessionActive = true;

      if (!this.currentUserName) {
        this.currentUserName = room.hostName;
      }

      this.messages = [
        {
          id: 1,
          sender: 'AI Mediator',
          role: 'ai',
          time: this.formatTime(new Date()),
          isAI: true,
          text: `Welcome to room ${room.code}. The mediation session is ready. Participants can now discuss the situation respectfully.`,
        },
      ];
    } catch (error) {
      console.error('Unable to load room:', error);
      this.sessionActive = false;
      this.router.navigate(['/']);
    } finally {
      this.isLoading = false;
      this.cdr.detectChanges();
    }

    const room = await this.roomsService.getRoom(this.roomCode);

    this.roomCode = room.code;
    this.participants = room.participants;
    this.sessionActive = true;

    this.connectToLiveRoomUpdates();
  }

  private connectToLiveRoomUpdates(): void {
    this.roomSocket?.close();

    this.roomSocket = this.roomsService.connectToRoomUpdates(
      this.roomCode,
      (room) => {
        this.roomCode = room.code;
        this.participants = room.participants;
        this.sessionActive = true;
        this.cdr.detectChanges();
      },
      (message) => {
        console.error(message);
        this.sessionActive = false;
        this.cdr.detectChanges();
      },
    );
  }

  ngAfterViewChecked(): void {
    this.scrollToBottom();
  }

  scrollToBottom(): void {
    try {
      const el = this.messagesContainer.nativeElement;
      el.scrollTop = el.scrollHeight;
    } catch {
      // Ignore if view is not ready yet.
    }
  }

  copyCode(): void {
    navigator.clipboard.writeText(this.roomCode);
    this.codeCopied = true;
    setTimeout(() => {
      this.codeCopied = false;
      this.cdr.detectChanges();
    }, 2000);
  }

  sendMessage(): void {
    const text = this.newMessage.trim();
    if (!text) return;

    const participant = this.getCurrentParticipant();

    this.messages.push({
      id: this.messages.length + 1,
      sender: participant?.name ?? this.currentUserName ?? 'Guest',
      role: participant?.role ?? 'Participant',
      time: this.formatTime(new Date()),
      text,
    });

    this.newMessage = '';
    this.cdr.detectChanges();
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  getInitial(sender: string): string {
    const participant = this.participants.find((p) => p.name === sender);
    return participant?.initial ?? sender.charAt(0).toUpperCase();
  }

  getAvatarColor(roleOrSender: string): string {
    const participant = this.participants.find(
      (p) => p.role === roleOrSender || p.name === roleOrSender,
    );

    if (participant) {
      return participant.color;
    }

    if (roleOrSender === 'ai') {
      return '#3b82f6';
    }

    return '#6b7280';
  }

  setTab(tab: 'public' | 'private' | 'agreement'): void {
    this.activeTab = tab;
  }

  private getCurrentParticipant(): RoomParticipant | undefined {
    return this.participants.find((p) => p.name === this.currentUserName);
  }

  private formatTime(date: Date): string {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
  }
}