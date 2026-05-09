import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class HomeComponent {

  constructor(private router: Router) {}

  createRoom(): void {
    this.router.navigate(['/create-room']);
  }

  joinRoom(): void {
    this.router.navigate(['/join-room']);
  }
}