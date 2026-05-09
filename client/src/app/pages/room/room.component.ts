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
import {
  RoomsService,
  RoomParticipant,
  RoomState,
  ChatMessage,
  InsightPoint,
} from '../../services/rooms.service';

export interface Message {
  sender: string;
  role: string;
  time: string;
  text: string;
  isAI?: boolean;
}

export interface RoomInsights {
  reply: string;
  agreements: InsightPoint[];
  disagreements: InsightPoint[];
  compromises: InsightPoint[];
}

@Component({
  selector: 'app-room',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './room.component.html',
  styleUrls: ['./room.component.scss'],
})
export class RoomComponent implements OnInit, AfterViewChecked, OnDestroy {
  @ViewChild('messagesContainer') messagesContainer!: ElementRef<HTMLElement>;

  roomCode = 'UNKNOWN';
  currentUserName = '';

  sessionActive = false;
  activeTab: 'public' | 'private' | 'agreement' = 'public';
  newMessage = '';
  codeCopied = false;
  isLoading = true;
  isSending = false;

  participants: RoomParticipant[] = [];

  publicMessages: Message[] = [];
  privateMessages: Message[] = [];
  visibleMessages: Message[] = [];
  privateHistory: ChatMessage[] = [];

  insights: RoomInsights = {
    reply: '',
    agreements: [],
    disagreements: [],
    compromises: [],
  };

  chatTitle = 'Public mediation';
  chatSubtitle = 'Messages are shared with the room in real time.';
  chatPlaceholder = 'Type your message to the room...';
  chatNotice = 'All public messages are recorded and shared instantly.';
  emptyStateTitle = 'No public messages yet';
  emptyStateText = 'Start the discussion and the mediator will update the summary on the right.';

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

      this.applyRoomState(room);

      if (!this.currentUserName) {
        this.currentUserName = room.hostName;
      }

      this.sessionActive = true;
    } catch (error) {
      console.error('Unable to load room:', error);
      this.sessionActive = false;
      this.router.navigate(['/']);
    } finally {
      this.isLoading = false;
      this.cdr.detectChanges();
    }

    this.connectToLiveRoomUpdates();
  }

  private connectToLiveRoomUpdates(): void {
    this.roomSocket?.close();

    this.roomSocket = this.roomsService.connectToRoomUpdates(
      this.roomCode,
      (room) => {
        this.applyRoomState(room);
        this.sessionActive = true;
        this.cdr.detectChanges();
        this.scrollToBottom();
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

  async sendMessage(): Promise<void> {
    const text = this.newMessage.trim();
    if (!text || this.isSending) return;

    this.newMessage = '';

    if (this.activeTab === 'private') {
      await this.sendPrivateMessage(text);
      return;
    }

    this.sendPublicMessage(text);
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

    if (roleOrSender === 'ai' || roleOrSender.toLowerCase().includes('ai')) {
      return '#3b82f6';
    }

    return '#6b7280';
  }

  setTab(tab: 'public' | 'private' | 'agreement'): void {
    this.activeTab = tab;
    this.refreshTabView();
    this.cdr.detectChanges();
  }

  private getCurrentParticipant(): RoomParticipant | undefined {
    return this.participants.find((p) => p.name === this.currentUserName);
  }

  private getCurrentDisplayName(): string {
    return this.getCurrentParticipant()?.name ?? this.currentUserName ?? 'Guest';
  }

  private applyRoomState(room: RoomState): void {
    this.roomCode = room.code;
    this.participants = room.participants;
    this.publicMessages = (room.publicMessages ?? []).map((message) => ({
      sender: message.sender,
      role: message.role,
      time: message.time,
      text: message.text,
      isAI: message.isAI,
    }));

    this.insights = {
      reply: room.insights?.reply ?? '',
      agreements: room.insights?.agreements ?? [],
      disagreements: room.insights?.disagreements ?? [],
      compromises: room.insights?.compromises ?? [],
    };

    this.refreshTabView();
  }

  private refreshTabView(): void {
    if (this.activeTab === 'public') {
      this.chatTitle = 'Public mediation';
      this.chatSubtitle = 'Everyone in the room sees these messages instantly.';
      this.chatPlaceholder = 'Write to the public room...';
      this.chatNotice = 'Messages are synchronized in real time over WebSocket.';
      this.emptyStateTitle = 'No public messages yet';
      this.emptyStateText = 'Start the conversation. The mediator will update the right panel as the discussion evolves.';
      this.visibleMessages = [...this.publicMessages];
      return;
    }

    if (this.activeTab === 'private') {
      this.chatTitle = 'Private chat';
      this.chatSubtitle = 'Only you and the mediator see this thread.';
      this.chatPlaceholder = 'Ask the mediator privately...';
      this.chatNotice = 'Private messages are not broadcast to the other party.';
      this.emptyStateTitle = 'Private chat is empty';
      this.emptyStateText = 'Use this space to ask the mediator for help without sharing it publicly.';
      this.visibleMessages = [...this.privateMessages];
      return;
    }

    this.chatTitle = 'Agreement draft';
    this.chatSubtitle = 'A synthesized draft based on the current conversation.';
    this.chatPlaceholder = 'Add a note to the draft...';
    this.chatNotice = 'This view reflects the current mediation summary.';
    this.emptyStateTitle = 'No agreement draft yet';
    this.emptyStateText = 'Keep discussing in public or private chat and the draft will update automatically.';
    this.visibleMessages = this.buildAgreementMessages();
  }

  private buildAgreementMessages(): Message[] {
    const draftText =
      this.insights.reply ||
      'The mediator will generate an agreement draft after the public discussion starts.';

    return [
      {
        sender: 'AI Mediator',
        role: 'ai',
        time: this.formatTime(new Date()),
        text: draftText,
        isAI: true,
      },
    ];
  }

  private sendPublicMessage(text: string): void {
    const sender = this.getCurrentDisplayName();

    if (!this.roomSocket || this.roomSocket.readyState !== WebSocket.OPEN) {
      this.publicMessages = [
        ...this.publicMessages,
        {
          sender,
          role: 'participant',
          time: this.formatTime(new Date()),
          text,
        },
      ];
      this.refreshTabView();
      this.cdr.detectChanges();
      return;
    }

    this.roomsService.sendPublicMessage(this.roomSocket, sender, text);
  }

  private async sendPrivateMessage(text: string): Promise<void> {
    const sender = this.getCurrentDisplayName();
    const historyBeforeSend = [...this.privateHistory];

    this.isSending = true;
    this.privateMessages = [
      ...this.privateMessages,
      {
        sender,
        role: 'user',
        time: this.formatTime(new Date()),
        text,
      },
    ];
    this.privateHistory = [
      ...this.privateHistory,
      { role: 'user', content: text },
    ];
    this.refreshTabView();
    this.cdr.detectChanges();

    try {
      const response = await this.roomsService.sendPrivateMessage(
        text,
        historyBeforeSend,
        this.roomCode,
        sender,
      );

      this.privateMessages = [
        ...this.privateMessages,
        {
          sender: 'AI Mediator',
          role: 'model',
          time: this.formatTime(new Date()),
          text: response.reply,
          isAI: true,
        },
      ];
      this.privateHistory = [
        ...this.privateHistory,
        { role: 'model', content: response.reply },
      ];
    } catch (error) {
      console.error('Private chat request failed:', error);

      this.privateMessages = [
        ...this.privateMessages,
        {
          sender: 'AI Mediator',
          role: 'model',
          time: this.formatTime(new Date()),
          text: 'The private mediator is temporarily unavailable. Please try again in a moment.',
          isAI: true,
        },
      ];
    } finally {
      this.isSending = false;
      this.refreshTabView();
      this.cdr.detectChanges();
      this.scrollToBottom();
    }
  }

  private formatTime(date: Date): string {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
  }
}