import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { supabase } from '../lib/supabase'

const useAuthStore = create(
  persist(
    (set, get) => ({
      // ── State ──────────────────────────────────────────────
      user: null,       // full public.users row
      session: null,    // supabase auth session object
      role: null,       // 'doctor' | 'patient'
      isLoading: false,

      // ── Actions ────────────────────────────────────────────

      /**
       * Sign in with email + password, then fetch the public.users profile row.
       */
      login: async (email, password) => {
        set({ isLoading: true })
        try {
          const { data: authData, error: authError } =
            await supabase.auth.signInWithPassword({ email, password })

          if (authError) throw authError

          const authUser = authData?.user
          if (!authUser) throw new Error('Authentication failed: no user returned.')

          // Fetch full profile from public.users
          const { data: profile, error: profileError } = await supabase
            .from('users')
            .select('*')
            .eq('id', authUser.id)
            .single()

          if (profileError) throw profileError
          if (!profile) throw new Error('User profile not found in database.')

          set({
            session: authData.session,
            user: profile,
            role: profile.role,
            isLoading: false,
          })

          return { user: profile, role: profile.role }
        } catch (err) {
          set({ isLoading: false })
          throw err
        }
      },

      /**
       * Sign out and clear all auth state.
       */
      logout: async () => {
        set({ isLoading: true })
        await supabase.auth.signOut()
        set({ user: null, session: null, role: null, isLoading: false })
      },

      /**
       * Re-fetch the public.users row for the currently authenticated user
       * and update the store. Useful after profile mutations.
       */
      refreshUser: async () => {
        const { data: { user: authUser }, error } = await supabase.auth.getUser()
        if (error || !authUser) return

        const { data: profile, error: profileError } = await supabase
          .from('users')
          .select('*')
          .eq('id', authUser.id)
          .single()

        if (!profileError && profile) {
          set({ user: profile, role: profile.role })
        }
      },
    }),
    {
      name: 'nakshatra-auth',          // localStorage key
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        // Only persist the lightweight identifiers — session will be
        // re-validated by Supabase on load.
        user: state.user,
        role: state.role,
      }),
    }
  )
)

export default useAuthStore
