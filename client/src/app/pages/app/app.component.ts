import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RoomsService } from '../../services/rooms.service';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class HomeComponent {
  showJoinModal = false;
  joinCode = '';
  joinName = '';
  joinError = '';
  isJoining = false;

  // Input segments for the 3+4 code format (e.g. "MTN-4782")
  codeParts = ['', '', '', '', '', '', ''];

  constructor(
    private router: Router,
    private roomsService: RoomsService,
  ) {}

  createRoom(): void {
    this.router.navigate(['/create-room']);
  }

  openJoinModal(): void {
    this.showJoinModal = true;
    this.joinCode = '';
    this.joinName = '';
    this.joinError = '';
    this.codeParts = ['', '', '', '', '', '', ''];
  }

  closeJoinModal(): void {
    this.showJoinModal = false;
  }

  onCodeInput(event: Event, index: number): void {
    const input = event.target as HTMLInputElement;
    const value = input.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
    this.codeParts[index] = value.charAt(0);
    input.value = this.codeParts[index];

    // Auto-advance to next input
    if (value && index < 6) {
      const next = document.getElementById(`code-input-${index + 1}`);
      if (next) (next as HTMLInputElement).focus();
    }

    this.joinCode = this.getFullCode();
    this.joinError = '';
  }

  onCodeKeydown(event: KeyboardEvent, index: number): void {
    if (event.key === 'Backspace' && !this.codeParts[index] && index > 0) {
      const prev = document.getElementById(`code-input-${index - 1}`);
      if (prev) (prev as HTMLInputElement).focus();
    }
  }

  onCodePaste(event: ClipboardEvent): void {
    event.preventDefault();
    const pasted = (event.clipboardData?.getData('text') ?? '')
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '');

    // Fill in up to 7 chars (skip the dash position)
    for (let i = 0; i < 7 && i < pasted.length; i++) {
      this.codeParts[i] = pasted[i];
    }
    this.joinCode = this.getFullCode();

    // Focus last filled input
    const lastIndex = Math.min(pasted.length - 1, 6);
    const el = document.getElementById(`code-input-${lastIndex}`);
    if (el) (el as HTMLInputElement).focus();
  }

  getFullCode(): string {
    const letters = this.codeParts.slice(0, 3).join('');
    const digits  = this.codeParts.slice(3, 7).join('');
    if (!letters && !digits) return '';
    if (!digits) return letters;
    return `${letters}-${digits}`;
  }

  get isCodeComplete(): boolean {
    return this.codeParts.slice(0, 3).every(p => /[A-Z]/.test(p)) &&
           this.codeParts.slice(3, 7).every(p => /[0-9]/.test(p));
  }

  async joinRoom(): Promise<void> {
    if (!this.isCodeComplete || !this.joinName.trim()) {
      this.joinError = 'Please fill in all fields.';
      return;
    }

    this.isJoining = true;
    this.joinError = '';

    try {
      const room = await this.roomsService.joinRoom({
        code: this.joinCode,
        name: this.joinName.trim(),
      });

      this.showJoinModal = false;
      this.router.navigate(['/room'], {
        queryParams: { code: room.code, name: this.joinName.trim() }
      });
    } catch (error) {
      this.joinError = error instanceof Error ? error.message : 'Unable to join room.';
    } finally {
      this.isJoining = false;
    }
  }

  onOverlayClick(event: MouseEvent): void {
    if ((event.target as HTMLElement).classList.contains('modal-overlay')) {
      this.closeJoinModal();
    }
  }
}