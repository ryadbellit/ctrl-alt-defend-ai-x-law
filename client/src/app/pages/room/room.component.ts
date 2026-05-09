import { Component, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

export interface Message {
  id: number;
  sender: string;
  role: 'ai' | 'tenant' | 'landlord';
  time: string;
  text: string;
  isAI?: boolean;
}

export interface Participant {
  name: string;
  role: string;
  initial: string;
  color: string;
  online: boolean;
}

export interface InsightPoint {
  text: string;
}

@Component({
  selector: 'app-room',
  templateUrl: './room.component.html',
  styleUrls: ['./room.component.scss']
})
export class RoomComponent implements OnInit, AfterViewChecked {
  @ViewChild('messagesContainer') messagesContainer!: ElementRef;

  roomCode = 'MTN-4782';
  roomTitle = 'Public Mediation';
  roomSubtitle = 'Landlord-Tenant Heating Dispute';
  sessionActive = true;
  activeTab: 'public' | 'private' | 'agreement' = 'public';
  newMessage = '';
  codeCopied = false;

  participants: Participant[] = [
    { name: 'Sarah Chen', role: 'Tenant', initial: 'S', color: '#e879f9', online: true },
    { name: 'Mark Rodriguez', role: 'Landlord', initial: 'M', color: '#a855f7', online: true },
    { name: 'AI Mediator', role: 'Facilitator', initial: 'O', color: '#3b82f6', online: true },
  ];

  messages: Message[] = [
    {
      id: 1,
      sender: 'AI Mediator',
      role: 'ai',
      time: '2:34 PM',
      isAI: true,
      text: "Welcome to your mediation session. I'm here to facilitate a fair and productive conversation. Each party will have the opportunity to share their perspective. Let's begin by having Sarah share her main concerns."
    },
    {
      id: 2,
      sender: 'Sarah Chen',
      role: 'tenant',
      time: '2:35 PM',
      text: "Thank you. I've been renting apartment 4B for 18 months. Last month, the heating stopped working completely. I reported it immediately, but it took 3 weeks to get it fixed. It was freezing, and I had to buy space heaters. I don't think I should pay full rent for that month."
    },
    {
      id: 3,
      sender: 'Mark Rodriguez',
      role: 'landlord',
      time: '2:37 PM',
      text: "I understand Sarah's frustration, but there were complications. The heating system needed a specialized part that was on backorder. I ordered it the same day she reported the issue. I also offered to reduce rent by 15% for that month."
    }
  ];

  sarahTone = 72;
  markTone = 58;

  agreements: InsightPoint[] = [
    { text: 'Heating issue was legitimate and disruptive' },
    { text: "Parts delay was beyond landlord's control" },
    { text: 'Some form of compensation is appropriate' },
  ];

  disagreements: InsightPoint[] = [
    { text: 'Amount of rent reduction (15% vs. higher)' },
    { text: 'Reimbursement for space heater expenses' },
  ];

  compromises: InsightPoint[] = [
    { text: '25–30% rent reduction for affected month' },
    { text: 'Partial reimbursement for space heater costs (~$80)' },
  ];

  ngOnInit(): void {}

  ngAfterViewChecked(): void {
    this.scrollToBottom();
  }

  scrollToBottom(): void {
    try {
      const el = this.messagesContainer.nativeElement;
      el.scrollTop = el.scrollHeight;
    } catch (e) {}
  }

  copyCode(): void {
    navigator.clipboard.writeText(this.roomCode);
    this.codeCopied = true;
    setTimeout(() => this.codeCopied = false, 2000);
  }

  sendMessage(): void {
    const text = this.newMessage.trim();
    if (!text) return;

    const now = new Date();
    const time = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

    this.messages.push({
      id: this.messages.length + 1,
      sender: 'Sarah Chen',
      role: 'tenant',
      time,
      text
    });

    this.newMessage = '';
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  getInitial(sender: string): string {
    if (sender === 'AI Mediator') return 'O';
    return sender.charAt(0);
  }

  getAvatarColor(role: string): string {
    const map: Record<string, string> = {
      ai: '#3b82f6',
      tenant: '#e879f9',
      landlord: '#a855f7',
    };
    return map[role] || '#6b7280';
  }

  setTab(tab: 'public' | 'private' | 'agreement'): void {
    this.activeTab = tab;
  }
}