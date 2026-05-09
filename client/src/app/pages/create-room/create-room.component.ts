import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { Router, RouterModule } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RoomsService } from '../../services/rooms.service';

@Component({
  selector: 'app-create-room',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './create-room.component.html',
  styleUrls: ['./create-room.component.scss']
})
export class CreateRoomComponent implements OnInit {
  roomCode = '';
  userName = '';
  isCreating = false;
  step: 'form' | 'ready' = 'form';
  codeCopied = false;

  constructor(
    private router: Router,
    private roomsService: RoomsService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.roomCode = this.generateCode();
  }

  generateCode(): string {
    const letters = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
    const prefix = Array.from({ length: 3 }, () => letters[Math.floor(Math.random() * letters.length)]).join('');
    const suffix = Math.floor(1000 + Math.random() * 9000).toString();
    return `${prefix}-${suffix}`;
  }

  refreshCode(): void {
    this.roomCode = this.generateCode();
  }

  async createRoom(): Promise<void> {
    if (!this.userName.trim()) return;

    this.isCreating = true;
    this.cdr.detectChanges();

    try {
        const room = await this.roomsService.createRoom({
        name: this.userName.trim(),
        code: this.roomCode,
        });

        this.roomCode = room.code;
        this.step = 'ready';
    } catch (error) {
        console.error('Failed to create room:', error);
        this.step = 'form';
    } finally {
        this.isCreating = false;
        this.cdr.detectChanges();
    }
  }

  copyCode(): void {
    navigator.clipboard.writeText(this.roomCode);
    this.codeCopied = true;
    setTimeout(() => this.codeCopied = false, 2000);
  }

  enterRoom(): void {
    this.router.navigate(['/room'], {
      queryParams: { 
        code: this.roomCode,
        name: this.userName.trim(),
    },
    });
  }

  goBack(): void {
    this.router.navigate(['/']);
  }
}