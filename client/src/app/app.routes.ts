import { Routes } from '@angular/router';
import { HomeComponent } from './pages/app/app.component';
import { CreateRoomComponent } from './pages/create-room/create-room.component';
import { RoomComponent } from './pages/room/room.component';

export const routes: Routes = [
	{ path: '', component: HomeComponent },
	{ path: 'create-room', component: CreateRoomComponent },
	{ path: 'room', component: RoomComponent },
	{ path: '**', redirectTo: '' }
];
