import React, { useState } from 'react';
import { View, Text, Switch, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';

export type DayHours = { open: string; close: string } | null;
export type WeekSchedule = Record<string, DayHours>;

const DAYS: { key: string; label: string; short: string }[] = [
    { key: 'mon', label: 'Monday', short: 'Mon' },
    { key: 'tue', label: 'Tuesday', short: 'Tue' },
    { key: 'wed', label: 'Wednesday', short: 'Wed' },
    { key: 'thu', label: 'Thursday', short: 'Thu' },
    { key: 'fri', label: 'Friday', short: 'Fri' },
    { key: 'sat', label: 'Saturday', short: 'Sat' },
    { key: 'sun', label: 'Sunday', short: 'Sun' },
];

const DEFAULT_OPEN = '09:00';
const DEFAULT_CLOSE = '17:00';

export function emptySchedule(): WeekSchedule {
    return DAYS.reduce((acc, d) => ({ ...acc, [d.key]: null }), {});
}

/** "09:00" → "9:00am", so the summary reads the way a person would say it. */
function pretty(time: string): string {
    const [h, m] = time.split(':').map(Number);
    const suffix = h < 12 ? 'am' : 'pm';
    const hour = h % 12 === 0 ? 12 : h % 12;
    return m === 0 ? `${hour}${suffix}` : `${hour}:${String(m).padStart(2, '0')}${suffix}`;
}

/**
 * Collapse the week into something readable — "Mon-Fri 9am-5pm, Sat 10am-2pm,
 * Sun closed" — by grouping runs of days that share the same hours.
 */
export function summarise(schedule: WeekSchedule): string {
    const runs: { from: number; to: number; hours: DayHours }[] = [];
    DAYS.forEach((day, i) => {
        const hours = schedule[day.key] ?? null;
        const last = runs[runs.length - 1];
        const same = last
            && ((last.hours === null && hours === null)
                || (last.hours && hours && last.hours.open === hours.open && last.hours.close === hours.close));
        if (same) last.to = i;
        else runs.push({ from: i, to: i, hours });
    });

    return runs
        .map(({ from, to, hours }) => {
            const days = from === to
                ? DAYS[from].short
                : `${DAYS[from].short}-${DAYS[to].short}`;
            return hours ? `${days} ${pretty(hours.open)}-${pretty(hours.close)}` : `${days} closed`;
        })
        .join(', ');
}

export default function BusinessHoursEditor({
    schedule,
    onChange,
}: {
    schedule: WeekSchedule;
    onChange: (next: WeekSchedule) => void;
}) {
    const [editing, setEditing] = useState<{ day: string; field: 'open' | 'close' } | null>(null);

    const setDay = (key: string, hours: DayHours) => onChange({ ...schedule, [key]: hours });

    const applyToAll = () => {
        const monday = schedule.mon;
        onChange(DAYS.reduce((acc, d) => ({ ...acc, [d.key]: monday }), {}));
    };

    const current = editing ? schedule[editing.day] : null;
    const currentValue = (() => {
        const time = current ? current[editing!.field] : DEFAULT_OPEN;
        const [h, m] = time.split(':').map(Number);
        const d = new Date();
        d.setHours(h, m, 0, 0);
        return d;
    })();

    return (
        <View>
            {DAYS.map(({ key, label }) => {
                const hours = schedule[key];
                return (
                    <View key={key} style={styles.row}>
                        <Text style={styles.day}>{label}</Text>
                        {hours ? (
                            <View style={styles.times}>
                                <TouchableOpacity onPress={() => setEditing({ day: key, field: 'open' })}>
                                    <Text style={styles.time}>{pretty(hours.open)}</Text>
                                </TouchableOpacity>
                                <Text style={styles.dash}>–</Text>
                                <TouchableOpacity onPress={() => setEditing({ day: key, field: 'close' })}>
                                    <Text style={styles.time}>{pretty(hours.close)}</Text>
                                </TouchableOpacity>
                            </View>
                        ) : (
                            <Text style={styles.closed}>Closed</Text>
                        )}
                        <Switch
                            value={Boolean(hours)}
                            onValueChange={(on) =>
                                setDay(key, on ? { open: DEFAULT_OPEN, close: DEFAULT_CLOSE } : null)
                            }
                            trackColor={{ false: '#2A3A4C', true: '#25D366' }}
                            thumbColor="#FFFFFF"
                        />
                    </View>
                );
            })}

            <TouchableOpacity onPress={applyToAll} style={styles.applyAll}>
                <Text style={styles.applyAllText}>Use Monday&apos;s hours for every day</Text>
            </TouchableOpacity>

            {editing && (
                <DateTimePicker
                    value={currentValue}
                    mode="time"
                    display="default"
                    onChange={(event, selected) => {
                        const day = editing.day;
                        const field = editing.field;
                        if (Platform.OS === 'android') setEditing(null);
                        if (event.type === 'set' && selected) {
                            const time = `${String(selected.getHours()).padStart(2, '0')}:${String(selected.getMinutes()).padStart(2, '0')}`;
                            const existing = schedule[day] || { open: DEFAULT_OPEN, close: DEFAULT_CLOSE };
                            setDay(day, { ...existing, [field]: time });
                        }
                        if (Platform.OS !== 'android') setEditing(null);
                    }}
                />
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    row: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 10,
        borderBottomWidth: 1,
        borderBottomColor: '#1A2942',
    },
    day: { color: '#FFFFFF', fontSize: 15, width: 96 },
    times: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6 },
    time: {
        color: '#25D366',
        fontSize: 15,
        fontWeight: '600',
        paddingVertical: 4,
        paddingHorizontal: 8,
        backgroundColor: '#16273D',
        borderRadius: 8,
        overflow: 'hidden',
    },
    dash: { color: '#8899AA', fontSize: 15 },
    closed: { flex: 1, color: '#8899AA', fontSize: 15 },
    applyAll: { paddingVertical: 12 },
    applyAllText: { color: '#25D366', fontSize: 13, fontWeight: '600' },
});
