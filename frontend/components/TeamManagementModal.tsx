import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    Modal,
    StyleSheet,
    TouchableOpacity,
    ScrollView,
    TextInput,
    Alert,
    ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { teamAPI } from '../context/api';

interface TeamMember {
    id: string;
    name: string;
    email: string;
    phone_number?: string;
    role: string;
    status: string;
    invited_by: string;
    created_at: string;
    last_active?: string;
}

interface TeamManagementModalProps {
    visible: boolean;
    onClose: () => void;
    userRole: string;
    userId: string;
}

export default function TeamManagementModal({
    visible,
    onClose,
    userRole,
    userId,
}: TeamManagementModalProps) {
    const [members, setMembers] = useState<TeamMember[]>([]);
    const [loading, setLoading] = useState(false);
    const [inviteMode, setInviteMode] = useState(false);
    const [inviteName, setInviteName] = useState('');
    const [invitePhone, setInvitePhone] = useState('');
    const [inviteRole, setInviteRole] = useState('employee');
    const [saving, setSaving] = useState(false);

    const isOwner = userRole === 'owner';
    const isManager = userRole === 'manager' || isOwner;

    useEffect(() => {
        if (visible) {
            fetchMembers();
        }
    }, [visible]);

    const fetchMembers = async () => {
        setLoading(true);
        try {
            const data = await teamAPI.getMembers();
            setMembers(data);
        } catch (error) {
            console.error('Error fetching team members:', error);
            Alert.alert('Error', 'Failed to load team members');
        } finally {
            setLoading(false);
        }
    };

    const handleInvite = async () => {
        if (!inviteName.trim() || !invitePhone.trim()) {
            Alert.alert('Error', 'Please enter name and phone number');
            return;
        }

        if (invitePhone.trim().length < 8) {
            Alert.alert('Error', 'Please enter a valid phone number with country code (e.g. +254712345678)');
            return;
        }

        setSaving(true);
        const wasFirstMember = members.length === 0;
        
        try {
            await teamAPI.inviteMember({
                name: inviteName.trim(),
                phone_number: invitePhone.trim(),
                role: inviteRole,
            });
            
            // Show special message for first team member
            if (wasFirstMember) {
                Alert.alert(
                    '🎉 Team Features Unlocked!',
                    'You can now assign conversations, track activity, and collaborate with your team. Your app just got more powerful!',
                    [{ text: 'Awesome!', style: 'default' }]
                );
            } else {
                Alert.alert(
                    'Team Member Added!',
                    `${inviteName.trim()} has been added. They can now log in to the CRM app using their phone number (${invitePhone.trim()}) — no extra steps needed!`,
                    [{ text: 'Got it', style: 'default' }]
                );
            }
            
            setInviteMode(false);
            setInviteName('');
            setInvitePhone('');
            setInviteRole('employee');
            fetchMembers();
        } catch (error: any) {
            Alert.alert('Error', error.response?.data?.detail || 'Failed to invite team member');
        } finally {
            setSaving(false);
        }
    };

    const handleUpdateRole = async (memberId: string, currentRole: string) => {
        const roles = ['employee', 'manager'];
        const currentIndex = roles.indexOf(currentRole);
        const newRole = roles[(currentIndex + 1) % roles.length];

        try {
            await teamAPI.updateMember(memberId, { role: newRole });
            Alert.alert('Success', `Role updated to ${newRole}`);
            fetchMembers();
        } catch (error: any) {
            Alert.alert('Error', error.response?.data?.detail || 'Failed to update role');
        }
    };

    const handleToggleStatus = async (memberId: string, currentStatus: string) => {
        const newStatus = currentStatus === 'active' ? 'suspended' : 'active';

        try {
            await teamAPI.updateMember(memberId, { status: newStatus });
            Alert.alert('Success', `Member ${newStatus}`);
            fetchMembers();
        } catch (error: any) {
            Alert.alert('Error', error.response?.data?.detail || 'Failed to update status');
        }
    };

    const handleRemove = (member: TeamMember) => {
        Alert.alert(
            'Remove Team Member',
            `Remove ${member.name} from your team? They will lose access immediately.`,
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Remove',
                    style: 'destructive',
                    onPress: async () => {
                        try {
                            await teamAPI.removeMember(member.id);
                            Alert.alert('Success', 'Team member removed');
                            fetchMembers();
                        } catch (error: any) {
                            Alert.alert('Error', error.response?.data?.detail || 'Failed to remove member');
                        }
                    },
                },
            ]
        );
    };

    const getRoleColor = (role: string) => {
        switch (role) {
            case 'owner': return '#FFD700';
            case 'manager': return '#4A90D9';
            case 'employee': return '#25D366';
            default: return '#8899AA';
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'active': return '#25D366';
            case 'invited': return '#FF9800';
            case 'suspended': return '#FF6B6B';
            default: return '#8899AA';
        }
    };

    return (
        <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
            <SafeAreaView style={styles.container}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={onClose}>
                        <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>Team Management</Text>
                    {isManager && !inviteMode ? (
                        <TouchableOpacity onPress={() => setInviteMode(true)}>
                            <Ionicons name="person-add" size={24} color="#25D366" />
                        </TouchableOpacity>
                    ) : (
                        <View style={{ width: 24 }} />
                    )}
                </View>

                {inviteMode ? (
                    <ScrollView style={styles.content}>
                        <View style={styles.inviteForm}>
                            <Text style={styles.sectionTitle}>Invite Team Member</Text>

                            <View style={styles.formGroup}>
                                <Text style={styles.label}>Name *</Text>
                                <TextInput
                                    style={styles.input}
                                    value={inviteName}
                                    onChangeText={setInviteName}
                                    placeholder="John Doe"
                                    placeholderTextColor="#556"
                                />
                            </View>

                            <View style={styles.formGroup}>
                                <Text style={styles.label}>Phone Number *</Text>
                                <TextInput
                                    style={styles.input}
                                    value={invitePhone}
                                    onChangeText={setInvitePhone}
                                    placeholder="+254712345678"
                                    placeholderTextColor="#556"
                                    keyboardType="phone-pad"
                                    autoCapitalize="none"
                                />
                                <Text style={{ fontSize: 12, color: '#8899AA', marginTop: 4 }}>
                                    They'll log in with this number — no password needed
                                </Text>
                            </View>

                            <View style={styles.formGroup}>
                                <Text style={styles.label}>Role</Text>
                                <View style={styles.roleSelector}>
                                    <TouchableOpacity
                                        style={[styles.roleOption, inviteRole === 'employee' && styles.roleOptionActive]}
                                        onPress={() => setInviteRole('employee')}
                                    >
                                        <Text style={[styles.roleOptionText, inviteRole === 'employee' && styles.roleOptionTextActive]}>
                                            Employee
                                        </Text>
                                    </TouchableOpacity>
                                    <TouchableOpacity
                                        style={[styles.roleOption, inviteRole === 'manager' && styles.roleOptionActive]}
                                        onPress={() => setInviteRole('manager')}
                                    >
                                        <Text style={[styles.roleOptionText, inviteRole === 'manager' && styles.roleOptionTextActive]}>
                                            Manager
                                        </Text>
                                    </TouchableOpacity>
                                </View>
                            </View>

                            <View style={styles.roleInfo}>
                                <Text style={styles.roleInfoTitle}>
                                    {inviteRole === 'employee' ? 'Employee' : 'Manager'} Permissions:
                                </Text>
                                {inviteRole === 'employee' ? (
                                    <>
                                        <Text style={styles.roleInfoItem}>• Reply to assigned chats</Text>
                                        <Text style={styles.roleInfoItem}>• Create orders</Text>
                                        <Text style={styles.roleInfoItem}>• View assigned customers</Text>
                                    </>
                                ) : (
                                    <>
                                        <Text style={styles.roleInfoItem}>• All employee permissions</Text>
                                        <Text style={styles.roleInfoItem}>• Invite employees</Text>
                                        <Text style={styles.roleInfoItem}>• Assign conversations</Text>
                                        <Text style={styles.roleInfoItem}>• View activity logs</Text>
                                    </>
                                )}
                            </View>

                            <View style={styles.buttonRow}>
                                <TouchableOpacity
                                    style={[styles.button, styles.buttonSecondary]}
                                    onPress={() => {
                                        setInviteMode(false);
                                        setInviteName('');
                                        setInvitePhone('');
                                        setInviteRole('employee');
                                    }}
                                >
                                    <Text style={styles.buttonSecondaryText}>Cancel</Text>
                                </TouchableOpacity>
                                <TouchableOpacity
                                    style={[styles.button, styles.buttonPrimary, saving && styles.buttonDisabled]}
                                    onPress={handleInvite}
                                    disabled={saving}
                                >
                                    {saving ? (
                                        <ActivityIndicator color="#FFF" size="small" />
                                    ) : (
                                        <Text style={styles.buttonPrimaryText}>Add Member</Text>
                                    )}
                                </TouchableOpacity>
                            </View>
                        </View>
                    </ScrollView>
                ) : (
                    <ScrollView style={styles.content}>
                        {loading ? (
                            <View style={styles.loadingContainer}>
                                <ActivityIndicator size="large" color="#25D366" />
                            </View>
                        ) : members.length === 0 ? (
                            <View style={styles.emptyContainer}>
                                <Ionicons name="people-outline" size={64} color="#556" />
                                <Text style={styles.emptyText}>No team members yet</Text>
                                {isManager && (
                                    <Text style={styles.emptySubtext}>Tap + to invite your first team member</Text>
                                )}
                            </View>
                        ) : (
                            <View style={styles.membersList}>
                                {members.map((member) => (
                                    <View key={member.id} style={styles.memberCard}>
                                        <View style={styles.memberHeader}>
                                            <View style={styles.memberInfo}>
                                                <Text style={styles.memberName}>{member.name}</Text>
                                                <Text style={styles.memberEmail}>
                                                    {member.phone_number || member.email || '—'}
                                                </Text>
                                                {member.status === 'invited' && (
                                                    <Text style={{ fontSize: 11, color: '#FF9800', marginTop: 2 }}>
                                                        Pending first login
                                                    </Text>
                                                )}
                                            </View>
                                            <View style={styles.memberBadges}>
                                                <View style={[styles.badge, { backgroundColor: getRoleColor(member.role) + '20' }]}>
                                                    <Text style={[styles.badgeText, { color: getRoleColor(member.role) }]}>
                                                        {member.role}
                                                    </Text>
                                                </View>
                                                <View style={[styles.badge, { backgroundColor: getStatusColor(member.status) + '20' }]}>
                                                    <Text style={[styles.badgeText, { color: getStatusColor(member.status) }]}>
                                                        {member.status}
                                                    </Text>
                                                </View>
                                            </View>
                                        </View>

                                        {member.role !== 'owner' && isManager && (
                                            <View style={styles.memberActions}>
                                                {isOwner && (
                                                    <TouchableOpacity
                                                        style={styles.actionButton}
                                                        onPress={() => handleUpdateRole(member.id, member.role)}
                                                    >
                                                        <Ionicons name="swap-horizontal" size={18} color="#4A90D9" />
                                                        <Text style={styles.actionButtonText}>Change Role</Text>
                                                    </TouchableOpacity>
                                                )}
                                                {isOwner && member.status !== 'invited' && (
                                                    <TouchableOpacity
                                                        style={styles.actionButton}
                                                        onPress={() => handleToggleStatus(member.id, member.status)}
                                                    >
                                                        <Ionicons
                                                            name={member.status === 'active' ? 'pause' : 'play'}
                                                            size={18}
                                                            color="#FF9800"
                                                        />
                                                        <Text style={styles.actionButtonText}>
                                                            {member.status === 'active' ? 'Suspend' : 'Activate'}
                                                        </Text>
                                                    </TouchableOpacity>
                                                )}
                                                {isOwner && (
                                                    <TouchableOpacity
                                                        style={styles.actionButton}
                                                        onPress={() => handleRemove(member)}
                                                    >
                                                        <Ionicons name="trash-outline" size={18} color="#FF6B6B" />
                                                        <Text style={[styles.actionButtonText, { color: '#FF6B6B' }]}>Remove</Text>
                                                    </TouchableOpacity>
                                                )}
                                            </View>
                                        )}
                                    </View>
                                ))}
                            </View>
                        )}
                    </ScrollView>
                )}
            </SafeAreaView>
        </Modal>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#0A1628',
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 16,
        paddingVertical: 12,
        borderBottomWidth: 1,
        borderBottomColor: '#1A2942',
    },
    headerTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: '#FFFFFF',
    },
    content: {
        flex: 1,
    },
    loadingContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        paddingTop: 100,
    },
    emptyContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        paddingTop: 100,
    },
    emptyText: {
        fontSize: 18,
        fontWeight: '600',
        color: '#8899AA',
        marginTop: 16,
    },
    emptySubtext: {
        fontSize: 14,
        color: '#556',
        marginTop: 8,
    },
    inviteForm: {
        padding: 16,
    },
    sectionTitle: {
        fontSize: 20,
        fontWeight: '700',
        color: '#FFFFFF',
        marginBottom: 20,
    },
    formGroup: {
        marginBottom: 20,
    },
    label: {
        fontSize: 14,
        fontWeight: '600',
        color: '#8899AA',
        marginBottom: 8,
    },
    input: {
        backgroundColor: '#1A2942',
        borderRadius: 8,
        padding: 12,
        fontSize: 16,
        color: '#FFFFFF',
        borderWidth: 1,
        borderColor: '#2A3F5F',
    },
    roleSelector: {
        flexDirection: 'row',
        gap: 12,
    },
    roleOption: {
        flex: 1,
        paddingVertical: 12,
        paddingHorizontal: 16,
        borderRadius: 8,
        backgroundColor: '#1A2942',
        borderWidth: 2,
        borderColor: '#2A3F5F',
        alignItems: 'center',
    },
    roleOptionActive: {
        borderColor: '#25D366',
        backgroundColor: '#25D36620',
    },
    roleOptionText: {
        fontSize: 14,
        fontWeight: '600',
        color: '#8899AA',
    },
    roleOptionTextActive: {
        color: '#25D366',
    },
    roleInfo: {
        backgroundColor: '#1A2942',
        borderRadius: 8,
        padding: 16,
        marginBottom: 20,
    },
    roleInfoTitle: {
        fontSize: 14,
        fontWeight: '600',
        color: '#FFFFFF',
        marginBottom: 8,
    },
    roleInfoItem: {
        fontSize: 13,
        color: '#8899AA',
        marginBottom: 4,
    },
    buttonRow: {
        flexDirection: 'row',
        gap: 12,
    },
    button: {
        flex: 1,
        paddingVertical: 14,
        borderRadius: 8,
        alignItems: 'center',
        justifyContent: 'center',
    },
    buttonPrimary: {
        backgroundColor: '#25D366',
    },
    buttonSecondary: {
        backgroundColor: '#1A2942',
        borderWidth: 1,
        borderColor: '#2A3F5F',
    },
    buttonDisabled: {
        opacity: 0.6,
    },
    buttonPrimaryText: {
        fontSize: 16,
        fontWeight: '600',
        color: '#FFFFFF',
    },
    buttonSecondaryText: {
        fontSize: 16,
        fontWeight: '600',
        color: '#8899AA',
    },
    membersList: {
        padding: 16,
    },
    memberCard: {
        backgroundColor: '#1A2942',
        borderRadius: 12,
        padding: 16,
        marginBottom: 12,
    },
    memberHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: 12,
    },
    memberInfo: {
        flex: 1,
    },
    memberName: {
        fontSize: 16,
        fontWeight: '600',
        color: '#FFFFFF',
        marginBottom: 4,
    },
    memberEmail: {
        fontSize: 13,
        color: '#8899AA',
    },
    memberBadges: {
        flexDirection: 'row',
        gap: 6,
    },
    badge: {
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 12,
    },
    badgeText: {
        fontSize: 11,
        fontWeight: '600',
        textTransform: 'capitalize',
    },
    memberActions: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
        borderTopWidth: 1,
        borderTopColor: '#2A3F5F',
        paddingTop: 12,
    },
    actionButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingVertical: 6,
        paddingHorizontal: 12,
        borderRadius: 6,
        backgroundColor: '#0D1B2A',
    },
    actionButtonText: {
        fontSize: 13,
        fontWeight: '500',
        color: '#8899AA',
    },
});
