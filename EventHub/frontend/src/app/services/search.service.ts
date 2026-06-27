import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class SearchService {
  private searchQuerySubject = new BehaviorSubject<string>('');
  private searchLocationSubject = new BehaviorSubject<string>('');
  
  searchQuery$ = this.searchQuerySubject.asObservable();
  searchLocation$ = this.searchLocationSubject.asObservable();

  setSearchQuery(query: string): void {
    this.searchQuerySubject.next(query);
  }

  setSearchLocation(location: string): void {
    this.searchLocationSubject.next(location);
  }

  get currentQuery(): string {
    return this.searchQuerySubject.value;
  }

  get currentLocation(): string {
    return this.searchLocationSubject.value;
  }
}
